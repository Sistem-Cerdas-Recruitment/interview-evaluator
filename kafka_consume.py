import json
import os
import requests
import logging
from kafka import KafkaConsumer
from dotenv import load_dotenv
from evaluation import evaluate_interview

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_technical(competences: list[str], transcripts: list[dict]):
    new_transcripts = {
        "behavioral": [],
        "technical": [],
    }
    # logger.info(competences)

    for i in range(len(competences)):
        # new_transcripts[i]= { "competence": competences[i] }


        transcript = transcripts[i]
        # logger.info(transcript)

        if transcript[-1]["question"].startswith("TECHNICAL:"):
            new_transcripts["behavioral"].append(transcript[:-1])
            new_transcripts["technical"].append(transcript[-1])
        else:
            new_transcripts["behavioral"].append(transcript)
            new_transcripts["technical"].append([])
    
    return new_transcripts

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

def send_results_back(interview_score: float, job_application_id: str):
    logger.info(f"Sending interview evaluation result back with job_app_id {job_application_id}")
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
    logger.info(f"Data sent with status code {response.status_code}")
    logger.info(response.content)


def consume_messages():
    consumer = KafkaConsumer(
        "interview-evaluation",
        bootstrap_servers=[os.environ["KAFKA_IP"]],
        auto_offset_reset='earliest',
        client_id="interview-evaluation-1",
        group_id="interview-evaluation",
        api_version=(0, 10, 2)
    )

    logger.info("Successfully connected to Kafka at", os.environ["KAFKA_IP"])

    for message in consumer:
        try:
            logger.info("A message is being processed")
            incoming_message = json.loads(message.value.decode("utf-8"))
            logger.info(incoming_message)

            transcript = extract_technical(incoming_message["competences"], incoming_message["transcript"])
            # logger.info(transcript)
            # competences, responses = extract_competences_and_responses(incoming_message["competences"], transcript["behavioral"])

            interview_score = evaluate_interview(incoming_message["competences"], transcript)
            logger.info(interview_score)

            send_results_back(interview_score, incoming_message["job_application_id"])
            # logger.info(score)


        except json.JSONDecodeError:
            logger.error("Failed to decode JSON from message:", message.value)
            logger.error("Continuing...")
            continue