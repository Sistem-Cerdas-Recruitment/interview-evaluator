import boto3
import os
import requests
import time
import logging
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])

# Function to loop through all items and print only the primary keys
def scan_table_keys_only():
    keys = []
    response = table.scan(
        ProjectionExpression='Tag'  # Only fetch the partition key
    )
    items = response.get('Items', [])
    
    for item in items:
        keys.append(item['Tag'])
    
    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(
            ProjectionExpression='Tag',
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        items = response.get('Items', [])
        
        for item in items:
            keys.append(item['Tag'])

    return keys

# Function to get an item from the table
def get_item(key):
    response = table.get_item(
        Key={
            'Tag': key
        }
    )
    return response.get('Item')

def huggingface_query(url, headers, payload):
	response = requests.post(url, headers=headers, json=payload)
	return response.json()

tags = scan_table_keys_only()

def extract_competences_and_responses(competences: list[str], transcripts: list[dict]):
    responses = []

    for i in range(len(competences)):
        transcript = transcripts[i]

        response = ""
        for idx, chat in enumerate(transcript):
            # logger.info(chat)
            response += chat["answer"]

            if idx < len(transcript) - 1:
                response += "\n"
        
        responses.append(response)
    
    return competences, responses

def evaluate_interview(competences: list[str], transcript: list):
    model_inputs = []
    responses = extract_competences_and_responses(competences, transcript["behavioral"])

    for i in range(len(competences)):
        competence = competences[i]
        response = responses[i]

        text = "KNOWLEDGE:\n"

        matching_tags_text_competence = {tag for tag in tags if tag in competence}
        matching_tags_text_response = {tag for tag in tags if tag in response}

        matching_tags = matching_tags_text_competence.union(matching_tags_text_response)

        knowledge_exist = False
        for tag in matching_tags:
            knowledge_text = get_item(tag)["Text"]
            if "UNKNOWN TAG" not in knowledge_text:
                text += knowledge_text
                text += "\n"
                knowledge_exist = True

        if not knowledge_exist:
            text +="None\n"

        text += f"\nCOMPETENCE: {competence}\n\n"

        text += f"RESPONSE:\n{response}"

        model_inputs.append(text)

    HUGGINGFACE_API_URL = os.environ["HUGGINGFACE_API_URL"]
    headers = {"Authorization": f"Bearer {os.environ['HUGGINGFACE_TOKEN']}"}

    result = huggingface_query(HUGGINGFACE_API_URL, headers, { "inputs": model_inputs })

    # Handling cold start
    if "error" in result:
        if result["error"] == os.environ["COLD_START_ERROR"]:
            logger.info("Cold start. Waiting 30 seconds.")
            time.sleep(30)
            result = huggingface_query(HUGGINGFACE_API_URL, headers, { "inputs": model_inputs })

    final_score = 0
    behavioral_scores = generate_behavioral_score(result)
    technical_scores = generate_technical_score(competences, transcript["technical"])

    final_score = aggregate_scores(behavioral_scores, technical_scores)

    return final_score

def aggregate_scores(b: list[int], t: list[int]):
    total_score = 0

    for i in range(len(b)):
        score = 0
        if t[i] != -1:
            score = (b[i] + t[i]) / 2

        else:
            score = b[i]

        total_score += score

    
    return (total_score / len(b)) * 100


def generate_behavioral_score(eval_array):
    logger.info(eval_array)
    # total_score = 0
    # logger.info(eval_array)
    scores = []

    for eval in eval_array:
        fail_score = 0
        success_score = 0

        if eval[0]["label"] == "FAIL":
            fail_score = eval[0]["score"]
        elif eval[0]["label"] == "SUCCESS":
            success_score = eval[0]["score"]

        if eval[1]["label"] == "FAIL":
            fail_score = eval[1]["score"]
        elif eval[1]["label"] == "SUCCESS":
            success_score = eval[1]["score"]

        if fail_score < success_score:
            scores.append(1)
        else:
            scores.append(0)
    
    return scores

client = OpenAI()

def generate_model_parameters(skill: str, transcript: str):
    model_parameters = {
  "model":"gpt-4-0125-preview",
  "messages":[
    {"role": "system", "content": f"""
You are tasked with evaluating a transcript of an IT job interview. The interview that is conducted in the transcript is technical. 
You need sufficient IT knowledge since you will evaluate the answer of the interviewee to determine whether the interviewee answer correctly or not.
You will output "SUCCESS" if the interviewee's answer is deemd correct and "FAIL" if it's deemed false.
Below are 5 examples of correct answers.
     
Here are 5 examples:
EXAMPLE 1:
SKILL TO BE EVALUATED: Python

INTERVIEWER:
What is the use of zip () in python?

INTERVIEWEE:
The zip returns an iterator and takes iterable as argument. These iterables can be list, tuple, dictionary etc. It maps similar index of every iterable to make a single entity.
    
OUTPUT: SUCCESS

EXAMPLE 2:
SKILL TO BE EVALUATED: Python

INTERVIEWER:
What will be the output of the following?
name=["swati","shweta"]
age=[10,20]
new_entity-zip(name,age)
new_entity-set(new_entity)
logger.info(new_entity)

INTERVIEWEE:
The output is {{('shweta', 20), ('swati', 10)}}

OUTPUT: SUCCESS

EXAMPLE 3:
SKILL TO BE EVALUATED: Python

INTERVIEWER:
What will be the output of the following?
a=["1","2","3"]
b=["a","b","c"]
c=[x+y for x, y in zip(a,b)] logger.info(c)

INTERVIEWEE:
The output is: ['1a', '2b', '3c']

OUTPUT: SUCCESS

EXAMPLE 4:
SKILL TO BE EVALUATED: Python

INTERVIEWER:
What will be the output of the following?
str="apple#banana#kiwi#orange"
logger.info(str.split("#",2))

INTERVIEWEE:
['apple', 'banana', 'kiwi#orange']

OUTPUT: SUCCESS

EXAMPLE 5:
SKILL TO BE EVALUATED: Python

INTERVIEWER:
What are python modules? Name some commonly used built-in modules in Python?

INTERVIEWEE:
Python modules are files containing Python code. This code can either be function classes or variables. A Python module is a .py file containing executable code. Some of thecommonly used built-in modules are:
- Os
- sys
- math
- random
- data time
- json

OUTPUT: SUCCESS

Note that the examples that I give above have the correct answer. Your job is to generate the output only (SUCCESS OR FAIL). You don't need to explain your justification.
SKILL TO BE EVALUATED: {skill}
{transcript}

"""},
  ]
}
    
    return model_parameters

def generate_technical_score(skills: str, transcript: str):
    # total_score = 0
    scores = []
    for idx, skill in enumerate(skills):
        
        chat = transcript[idx]
        if len(chat) > 0:
            transcript_text = f"INTERVIEWEE:\n{chat['question']}\n\nINTERVIEWER:\n{chat['answer']}"

            model_parameters = generate_model_parameters(skill, transcript_text)
            completion = client.chat.completions.create(
                **model_parameters
            )

            generated = completion.choices[0].message.content
            score = 1 if "SUCCESS" in generated else 0
            # total_score += score
            scores.append(score)
        else:
            scores.append(-1)

    return scores

# evaluate_interview(
#     ["Experience of working in a Linux environment"],
#     ["""Yes, in my previous role as a System Administrator, we had a major project aimed at migrating our web servers from Windows to a Linux-based platform. The objective was to improve the robustness, security, and scalability of our application hosting environment.


# I was responsible for designing the Linux server architecture, setting up the servers, and ensuring the seamless migration of all our applications from the Windows environment to Linux. This included configuring Apache web servers, setting up MySQL databases, and ensuring that all dependencies and libraries required by the applications were properly installed and configured.


# Firstly, I created a detailed migration plan outlining all the steps involved, from initial setup to final testing. I then set up the Linux servers, including installing the operating system, configuring network settings, and securing the servers against potential threats. I also wrote scripts to automate the deployment of our applications, which sped up the migration process and reduced human error. Throughout the project, I worked closely with the development team to troubleshoot any issues that arose during the migration.


# The migration was a success. We successfully moved all our applications to the new Linux environment with minimal downtime. Post-migration, we observed significant improvements in the performance and reliability of our web applications. Additionally, the project led to a reduction in operating costs, as the Linux servers required less maintenance and had lower licensing fees compared to our previous Windows servers. The success of the project also increased my proficiency and confidence in managing Linux environments."""]
# )


# try:
#     for i in range(df_len):
#         tag = df.loc[i]["Tag"]
#         text = df.loc[i]["Text"]

#         table.put_item(Item={"Tag": tag, "Text": text})
# finally:
#     pass