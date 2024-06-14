import json
import os
import requests
from kafka import KafkaConsumer
from dotenv import load_dotenv
from evaluation import evaluate_interview, generate_score

load_dotenv()

def extract_competences_and_responses(competences: list[str], transcripts: list[dict]):
    responses = []

    for i in range(len(competences)):
        transcript = transcripts[i]

        response = ""
        for idx, chat in enumerate(transcript):
            # print(chat)
            response += chat["answer"]

            if idx < len(transcript) - 1:
                response += "\n"
        
        responses.append(response)
    
    return competences, responses

def send_results_back(interview_score: float, job_application_id: str):
    print(f"Sending interview evaluation result back with job_app_id {job_application_id}")
    url = f"{os.environ['BACKEND_URL']}/api/interview/score"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": os.environ["X-API-KEY"]
    }

    body = {
        "job_application_id": job_application_id,
        "interview_score": interview_score
    }

    response = requests.patch(url, json=body, headers=headers)
    print(f"Data sent with status code {response.status_code}")
    print(response.content)


def consume_messages():
    consumer = KafkaConsumer(
        "interview-evaluation",
        bootstrap_servers=[os.environ["KAFKA_IP"]],
        auto_offset_reset='earliest',
        client_id="interview-evaluation-1",
        group_id="interview-evaluation",
        api_version=(0, 10, 2)
    )

    print("Successfully connected to Kafka at", os.environ["KAFKA_IP"])

    for message in consumer:
        try:
            print("A message is being processed")
            incoming_message = json.loads(message.value.decode("utf-8"))
            # print(incoming_message)

            competences, responses = extract_competences_and_responses(incoming_message["competence"], incoming_message["transcript"])
            result = evaluate_interview(competences, responses)

            interview_score = generate_score(result)

            send_results_back(interview_score, incoming_message["job_application_id"])
            # print(score)


        except json.JSONDecodeError:
            print("Failed to decode JSON from message:", message.value)
            print("Continuing...")
            continue