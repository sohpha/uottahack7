const express = require('express');
const twilio = require('twilio');
const Paho = require('paho-mqtt');
require('dotenv').config();
const app = express();

global.WebSocket = require('ws');

function sendSMSAlert(payload) {
    const accountSid = process.env.TWILIO_SID;
    const authToken = process.env.TWILIO_AUTH_TOKEN;
    const twilioClient = require('twilio')(accountSid, authToken);
    twilioClient.messages
        .create({
            body: payload,
            from: process.env.TWILIO_PHONE_NUMBER,
            to: process.env.DEST_PHONE_NUMBER
        })
        .then(message => console.log(message.sid));

}

const connectOptions = {
    userName: process.env.SOLACE_CLOUD_USERNAME,
    password: process.env.SOLACE_CLOUD_PWD,
}

function connect() {
  const client = new Paho.Client(process.env.SOLACE_CLOUD_HOST_URI, 'uid2');
  client.onMessageArrived = onMessageArrived;
  client.connect({
    ...connectOptions,
    onSuccess: () => {
        console.log("Connected successfully.");
        client.subscribe("userTopic", {
            onSuccess: () => {
                console.log("Subscribed successfully.")
            }
        });
    },
    onFailure: (err) => {
        console.error("Connection failed:", err.errorMessage);
    },
});
  
}

function onMessageArrived(message) {
  console.log("onMessageArrived: "+message.payloadString);
  //sendSMSAlert(message.payloadString.message); uncomment at end
}

connect();

app.listen(3000, () => console.log("Listening at port 3000"));
