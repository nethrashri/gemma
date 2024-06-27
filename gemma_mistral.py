import sqlite3
import streamlit as st
from langchain_community.llms import Ollama
import json
from datetime import datetime, timedelta

# In-memory cache for loaded models
model_cache = {}

# Function to load the models using Ollama
def load_models():
    if "gemma_llm" not in model_cache:
        model_cache["gemma_llm"] = Ollama(model="gemma:7b")
    if "mistral_llm" not in model_cache:
        model_cache["mistral_llm"] = Ollama(model="mistral:7b-instruct-q6_K")
    return model_cache["gemma_llm"], model_cache["mistral_llm"]

gemma_llm, mistral_llm = load_models()

# Function to query the home_details.db for available devices
def get_available_devices(hashid):
    query = "SELECT Hashid, LocationName, devicefriendName, macid, clusterid, devicetype FROM home_details WHERE Hashid = ?"
    with sqlite3.connect('home_details.db') as conn:
        cursor = conn.cursor()
        cursor.execute(query, (hashid,))
        devices = cursor.fetchall()
    return devices

# Function to generate the prompt for routine creation
def generate_routine_prompt(routine_type, hashid, devices):
    example_output = """
[
  {
    "routine_name": "morning",
    "devicetype": "light",
    "room_name": "bed room",
    "macid": "23213234",
    "time": "06:00",
    "status": "on",
    "com": [
      {
        "supportedclusid": 6,
        "supportedclus_val": "true"
      },
      {
        "supportedclusid": 8,
        "supportedclusid_val": 70
      },
      {
        "supportedclusid": 787,
        "supportedclus_val": "167"
      }
    ]
  },
  {
    "routine_name": "morning",
    "devicetype": "motion sensor",
    "room_name": "bed room",
    "macid": "23213237",
    "time": "06:15",
    "status": "off",
    "com": [
      {
        "supportedclusid": 6,
        "supportedclus_val": "false"
      }
    ]
  },
  {
    "routine_name": "morning",
    "devicetype": "thermostat",
    "room_name": "bed room",
    "macid": "232132378",
    "time": "06:30",
    "status": "on",
    "com": [
      {
        "supportedclusid": 6,
        "supportedclus_val": "true"
      }
    ]
  },
  {
    "routine_name": "morning",
    "devicetype": "smart blinds",
    "room_name": "bed room",
    "macid": "232132399",
    "time": "06:45",
    "status": "off",
    "com": [
      {
        "supportedclusid": 6,
        "supportedclus_val": "false"
      }
    ]
  }
]
"""
    context = f"""
You are a smart home assistant. You understand and control smart devices within a home environment, create routines, and show available devices in the home.

Humans, referred to as users, engage in various activities throughout their day. They live in homes equipped with multiple devices and follow different routines such as morning routines, evening routines, movie time routines, and party time routines. Each routine involves the use of specific devices in different rooms at specific times.

Imagine you are like Alexa, a smart home virtual assistant, providing suggestions for creating these routines. You need to check for available devices in the user's home and create routines based on the time and device mapping in the home_details.db.

For light devices, consider the following:
- When the status is 'on' or 'off', include a `supportedclusid` of 6 with a `supportedclus_val` of 'true' or 'false'.
- Suggest brightness when `supportedclusid` is 8, with `supportedclusid_val` between 0-100 (which represents brightness).
- Suggest color when `supportedclusid` is 787, with `supportedclus_val` between 0-100.

For thermostat and other devices, consider the following:
- Include only `supportedclusid` 6 with a `supportedclus_val` based on the status ('true' for on/open/up, 'false' for off/close/down).

Here are the available devices in the home of user with Hashid {hashid}: {devices}

Create a {routine_type} routine for the user with Hashid {hashid} in the following JSON format. Make sure to replace any placeholders like 'brightness_value' with actual values:
{example_output}
"""

    return context

# Function to generate a general query prompt with available devices
def generate_general_query_prompt(query, devices):
    available_devices = [device[5] for device in devices]
    device_list = ", ".join(set(available_devices))
    
    prompt = f"""
You are a smart home assistant. You understand and control smart devices within a home environment and respond to general user queries related to home automation.

User query: "{query}"

Here are the available devices in the user's home: {device_list}

Please respond appropriately to the user's request or query based on the available devices.
"""
    return prompt

# Function to handle general queries
def handle_general_query(query, hashid):
    devices = get_available_devices(hashid)
    if not devices:
        return "No devices found for the given Hashid."

    prompt = generate_general_query_prompt(query, devices)
    
    # Use Mistral to generate response
    try:
        response = mistral_llm(prompt)
    except Exception as e:
        st.error(f"Error while generating response: {e}")
        return "No response from the model due to an error."
    
    # Handle and format the response from the model
    try:
        if isinstance(response, str) and response.strip():
            response_text = response.strip()
            st.write("Model Response Raw:")
            st.text_area("Response:", response_text, height=300)
            
            # Identify actions based on devices and user query
            actions = identify_actions(query, response_text, devices)
            return actions
        else:
            return "No response from the model."
    except Exception as e:
        return f"Unexpected error occurred: {e}"

# Function to identify actions based on the response and available devices
def identify_actions(query, response_text, devices):
    actions = []
    
    for device in devices:
        if "thermostat" in device[5].lower() and ("cold" in query.lower() or "hot" in query.lower()):
            actions.append({
                "device": "thermostat",
                "action": "adjust temperature",
                "current_status_check": True
            })
        elif "light" in device[5].lower() and "dark" in query.lower():
            actions.append({
                "device": "light",
                "action": "turn on",
                "current_status_check": True
            })
        elif "motion sensor" in device[5].lower() and "away" in query.lower():
            actions.append({
                "device": "motion sensor",
                "action": "activate",
                "current_status_check": True
            })
        elif "smart blinds" in device[5].lower() and "sunny" in query.lower():
            actions.append({
                "device": "smart blinds",
                "action": "open",
                "current_status_check": True
            })
    
    if actions:
        return json.dumps(actions, indent=4)
    else:
        return "No relevant actions identified based on the available devices."

# Main function to create the routine
def create_routine(hashid, routine_type):
    devices = get_available_devices(hashid)
    if not devices:
        return "No devices found for the given Hashid."

    # Transform clusterid from string to list
    transformed_devices = []
    for device in devices:
        device = list(device)
        try:
            device[4] = json.loads(device[4])  # Convert clusterid from JSON string to list
        except json.JSONDecodeError:
            device[4] = []  # Default to an empty list if JSON decoding fails
        transformed_devices.append(tuple(device))
    
    prompt = generate_routine_prompt(routine_type, hashid, transformed_devices)
    
    # Use Gemma to generate response
    try:
        response = gemma_llm(prompt)
    except Exception as e:
        st.error(f"Error while generating response: {e}")
        return "No response from the model due to an error."

    # Handle and format the response from the model
    try:
        if isinstance(response, str) and response.strip():
            response_text = response.strip()
            st.write("Model Response Raw:")
            st.text_area("Response:", response_text, height=300)
            
            # Parse the JSON response
            try:
                parsed_data = json.loads(response_text)
                
                # Save to JSON file
                with open(f'{routine_type}_routine.json', 'w') as json_file:
                    json.dump(parsed_data, json_file, indent=4)
                
                st.write("Routine saved to JSON file.")
                return json.dumps(parsed_data, indent=4)
            except json.JSONDecodeError:
                return "Unexpected response format from the model."
        else:
            return "No response from the model."
    except Exception as e:
        return f"Unexpected error occurred: {e}"

# Streamlit UI
st.title("Home Automation Assistant")

query_type = st.selectbox("Select Query Type:", ["Routine", "General Query"])
hashid = st.text_input("Enter User Hashid (required for routines):")
routine_type = st.text_input("Enter Routine Type (e.g., morning, evening, party time, movie time):") if query_type == "Routine" else ""
general_query = st.text_input("Enter your query:") if query_type == "General Query" else ""

if st.button("Submit"):
    if query_type == "Routine":
        if hashid and routine_type:
            with st.spinner('Generating routine...'):
                routine_suggestion = create_routine(hashid, routine_type)
            st.text(routine_suggestion)
        else:
            st.warning("Please enter both a Hashid and a routine type.")
    else:
        if general_query and hashid:
            with st.spinner('Processing query...'):
                general_response = handle_general_query(general_query, hashid)
            st.text(general_response)
        else:
            st.warning("Please enter both a query and a Hashid.")
