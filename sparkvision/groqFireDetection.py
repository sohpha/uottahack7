import cv2
import base64
import time
import paho.mqtt.client as mqtt
import json
import configparser
from datetime import datetime
from groq import Groq
import socket


def load_config():
    config = configparser.ConfigParser()
    config.read('config.properties')
    filename = 'config.properties'
    read_ok = config.read(filename)
    
    return {
        'host': config.get('mqtt', 'host'),
        'port': config.getint('mqtt', 'port'),
        'username': config.get('mqtt', 'username'),
        'password': config.get('mqtt', 'password'),
        'groq_api_key': config.get('groq', 'api_key'),
    }

config = load_config()

MQTT_HOST = config['host']
MQTT_PORT = config['port']
MQTT_USER = config['username']
MQTT_PASSWORD = config['password']
GROQ_API_KEY = config['groq_api_key']

def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"Connected with result code {reason_code}")

def establish_solace_connection():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect

    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.tls_set()
    
    client.connect(MQTT_HOST, MQTT_PORT, 60)

    client.loop_start()

    return client

# ---------------------------------
# 1) Initialize Groq client
# ---------------------------------
groqClient = Groq(api_key=GROQ_API_KEY)

# ---------------------------------
# 2) Fire-like color detection
#    (simple HSV-based pre-check)
# ---------------------------------
def likely_has_flame_colors(frame, min_fire_pixels=3000):
    """
    Returns True if there are at least 'min_fire_pixels' in the typical
    fire color range. Adjust color bounds and pixel threshold as needed.
    """
    # Convert to HSV color space
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Rough color range for fire: 
    # - Lower bound could be near red/orange
    # - Upper bound includes orange/yellow
    # This is approximate! Adjust based on your environment.
    lower_bound = (0, 100, 100)     # (H, S, V)
    upper_bound = (40, 255, 255)

    # Create mask of all pixels within this HSV range
    mask = cv2.inRange(hsv, lower_bound, upper_bound)
    fire_pixels = cv2.countNonZero(mask)

    return fire_pixels > min_fire_pixels

# ---------------------------------
# 3) Encode a frame to base64
# ---------------------------------
def encode_frame_to_base64(frame):
    """
    Encodes an OpenCV image (numpy array) into a base64 string (JPEG).
    """
    ret, buffer = cv2.imencode('.jpg', frame)
    if not ret:
        return None
    base64_str = base64.b64encode(buffer).decode('utf-8')
    return base64_str

# ---------------------------------
# 4) Main script logic
# ---------------------------------
def main():
    client2 = establish_solace_connection()
    topic = 'userTopic'

    # Open webcam (0 for default, or 1,2... for other cams)
    video_capture = cv2.VideoCapture(0)
    if not video_capture.isOpened():
        print("Error: Unable to access the webcam.")
        return

    # For multi-frame checks: how many consecutive frames must indicate fire
    consecutive_fire_threshold = 1
    fire_detected_frames = 0

    try:
        while True:
            ret, frame = video_capture.read()
            if not ret:
                print("Error: Unable to capture frame from webcam.")
                break

            # 1) Quick color-based pre-check
            if likely_has_flame_colors(frame):
                # 2) If suspicious, call the Groq model
                base64_image = encode_frame_to_base64(frame)
                if not base64_image:
                    print("Error: Failed to encode frame to base64.")
                    continue

                # Ask the model for a direct yes/no
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "We are monitoring an environment where real fires are rare. "
                                    "Respond ONLY with 'Yes' if you see actual flames or smoke in "
                                    "this image, otherwise respond with 'No'."
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ]

                try:
                    response = groqClient.chat.completions.create(
                        model="llama-3.2-11b-vision-preview",
                        messages=messages
                    )
                except Exception as api_err:
                    print(f"Error during API call: {api_err}")
                    continue

                # Get the LLM's response
                result = response.choices[0].message.content.strip().lower()
                print("[LLM] Response:", result)

                if "yes" in result:
                    fire_detected_frames += 1
                else:
                    fire_detected_frames = 0  # reset if not consecutive
            else:
                # No suspicious color => reset
                fire_detected_frames = 0

            # 3) Check if we have consecutive frames
            if fire_detected_frames >= consecutive_fire_threshold:
                print("ALERT: Fire detected!")
                # You could do additional alerts (SMS/email) here
                # Then reset or keep it triggered
                alert_data = {
                    "message": "SPARKVISION ALERT: Fire Detected!",
                    "timestamp": datetime.now().isoformat(),
                }
                client2.publish(topic, json.dumps(alert_data))
                print(f"Published: {alert_data}")
                fire_detected_frames = 0

            # Optional: show the video feed 
            cv2.imshow("Webcam Feed", frame)

            # Wait for 1.5 seconds (40 calls per minute max)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            #time.sleep(1.5)
    finally:
        # Release resources
        video_capture.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
