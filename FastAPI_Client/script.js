let token = "";
let recognition;
let previousModel = "";


/* ------------------ REGISTER ------------------ */

async function register()
{
const username = document.getElementById("regUser").value;
const password = document.getElementById("regPass").value;

const response = await fetch("/register",
{
method: "POST",
headers:
{
"Content-Type":"application/json"
},
body: JSON.stringify(
{
username:username,
password:password
})
});

const data = await response.json();

if(response.ok)
{
 
token = data.access_token;
localStorage.setItem("token", token);

alert("Login Successful");
document.getElementById("authSection").style.display="none";
document.getElementById("mainApp").style.display="block";

}
else
{
alert(data.detail || "Registration failed");
}
}


/* ------------------ LOGIN ------------------ */

async function login()
{

const username = document.getElementById("loginUser").value;
const password = document.getElementById("loginPass").value;

const formData = new URLSearchParams();
formData.append("username",username);
formData.append("password",password);

const response = await fetch("/login",
{
method:"POST",
headers:
{
"Content-Type":"application/x-www-form-urlencoded"
},
body:formData
});

const data = await response.json();

if(response.ok)
{

token = data.access_token;
localStorage.setItem("token", token);

alert("Login Successful");

document.getElementById("authSection").style.display="none";
document.getElementById("mainApp").style.display="block";

loadModels();

}
else
{
alert("Login Failed");
}

}


/* ------------------ FILE UPLOAD ------------------ */

async function uploadFile()
{

const file = document.getElementById("fileInput").files[0];

const formData = new FormData();

formData.append("file",file);

const response = await fetch("/upload",
{
method:"POST",
headers:
{
Authorization:"Bearer "+token
},
body:formData
});

const data = await response.json();

alert(data.message);  // shows only the message string
}



/* ------------------ CHAT ------------------ */

async function sendQuestion()
{

const inputBox = document.getElementById("questionInput");

const question = inputBox.value;

if(!question.trim()) return;

addUserMessage(question);

inputBox.value = "";   // clears the input box

const model = "allam-2-7b";  // default model since local models combo removed

const inline = document.getElementById("refInline").checked;
const list = document.getElementById("refList").checked;

let refStyle = "both";
if (inline && !list) refStyle = "inline";
else if (!inline && list) refStyle = "list";
else if (!inline && !list) refStyle = "none";

const response = await fetch("/v1/chat/completions",
{
method:"POST",
headers:
{
"Content-Type":"application/json",
"Authorization":"Bearer " + token
},
body:JSON.stringify(
{
model:model,
reference_style: refStyle,
messages:[
{role:"user",content:question}
]
})
});


const data = await response.json();

const answer = data.choices[0].message.content;
//Clean unwanted model artifacts
let displayAnswer = answer
    .replace(/\[\d+\]/g, "")                         // remove [1], [2]
    .replace(/Note: Citation marker.*$/s, ""); 

addBotMessage(displayAnswer);
let cleanAnswer = answer
    .replace(/<[^>]*>/g, "")               // 
    .replace(/\([^)]*\.pdf[^)]*\)/gi, "")
    .replace(/\[\d+\]/g, "")
    .replace(/Note: Citation marker.*$/s, "")
    .replace(/\s+/g, " ")                 // 
    .trim();

cleanAnswer = cleanAnswer.split("References:")[0];

speak(cleanAnswer);
}

document.addEventListener("DOMContentLoaded", function() {

    document.getElementById("questionInput").addEventListener("keydown", function(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            sendQuestion();
        }
    });

});


/* ------------------ CHAT DISPLAY ------------------ */

function addUserMessage(text)
{

const chat = document.getElementById("chatWindow");

const div = document.createElement("div");

div.className="userMessage";

div.innerText=text;

chat.appendChild(div);

}


function addBotMessage(text)
{

const chat = document.getElementById("chatWindow");

const div = document.createElement("div");

div.className="botMessage";

div.innerHTML = text;

chat.appendChild(div);

}


/* ------------------ VOICE INPUT ------------------ */

function startVoice()
{

recognition = new webkitSpeechRecognition();

recognition.lang="en-US";

recognition.onresult=function(event)
{
document.getElementById("questionInput").value = event.results[0][0].transcript;
};

recognition.start();

}

function stopVoice()
{

if(recognition)
{
recognition.stop();
}

speechSynthesis.cancel();
}


/* ------------------ VOICE OUTPUT ------------------ */

function speak(text)
{

//STOP any previous speech to avoid vrvrvr noise
speechSynthesis.cancel();

const speech = new SpeechSynthesisUtterance(text);

speech.lang="en-US";

speechSynthesis.speak(speech);

}

function readChat()
{

const messages = document.getElementsByClassName("botMessage");

if(messages.length === 0) return;

const lastMessage = messages[messages.length - 1];

const chatText = lastMessage.innerText;

//Remove inline references from speaking
let cleanText = chatText
    .replace(/\([^)]*\.pdf[^)]*\)/gi, "")   // remove full inline refs
    .replace(/\[\d+\]/g, "");               // remove [1], [2]

//Remove References section from speaking
cleanText = cleanText.split("References:")[0];

speak(cleanText);

}

function saveChatAsPDF()
{
    const chatWindow = document.getElementById("chatWindow");

    const originalContent = chatWindow.innerHTML;

    const printWindow = window.open('', '', 'width=800,height=600');

    printWindow.document.write(`
        <html>
        <head>
            <title>Chat Export</title>
            <style>
                body { font-family: Arial; padding: 20px; }
                .userMessage { color: blue; margin: 5px 0; }
                .botMessage { color: black; margin: 5px 0; }
            </style>
        </head>
        <body>
            <h2>Chat History</h2>
            ${originalContent}
        </body>
        </html>
    `);

    printWindow.document.close();
    printWindow.print();
}
