import boto3
import os
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

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

def evaluate_interview(competences: list[str], responses: list[str]):
    model_inputs = []
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

    # print(result)
    return result

def generate_score(eval_array):
    total_score = 0
    # print(eval_array)

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
            total_score += 1
    
    return (total_score / len(eval_array)) * 100.0

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