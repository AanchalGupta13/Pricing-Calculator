document.getElementById("userInput").addEventListener("keypress", function(event) {
    if (event.key === "Enter") {
        sendMessage();
    }
});

async function sendMessage() {
    let userInput = document.getElementById("userInput").value.trim();
    if (!userInput) return;

    let messagesDiv = document.getElementById("messages");

    // Display user message
    messagesDiv.innerHTML += `<div class="user-message">👤 <b>You:</b> ${userInput}</div>`;

    let payload = JSON.stringify({ body: JSON.stringify({ query: userInput }) });

    try {
        let response = await fetch("https://jvopmaa40h.execute-api.us-east-1.amazonaws.com/prod/chatbot", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: payload,
        });

        let responseData = await response.json();

        if (responseData.body) {
            let parsedBody = JSON.parse(responseData.body);

            if (parsedBody.cost_estimate && Array.isArray(parsedBody.cost_estimate) && parsedBody.cost_estimate.length > 0) {
                let estimate = parsedBody.cost_estimate[0];

                let formattedResponse = `
                <div class="ai-message">
                    🤖 <b>AI:</b> Cost Estimate:
                    <table class="cost-table">
                        <tr><th>Parameter</th><th>Value</th></tr>
                        <tr><td>Instance Type</td><td>${estimate.InstanceType}</td></tr>
                        <tr><td>Storage</td><td>${estimate.Storage}</td></tr>
                        <tr><td>Database</td><td>${estimate.Database === "No" ? "No Database" : estimate.Database}</td></tr>
                        <tr><td>Monthly Server Cost</td><td>${estimate["Monthly Server Cost"]}</td></tr>
                        <tr><td>Monthly Storage Cost</td><td>${estimate["Monthly Storage Cost"]}</td></tr>
                        <tr><td>Monthly Database Cost</td><td>${estimate["Monthly Database Cost"]}</td></tr>
                        <tr><td><b>Total Pricing</b></td><td><b>${estimate["Total Pricing"]}</b></td></tr>
                    </table>
                </div>`;

                messagesDiv.innerHTML += formattedResponse;
            } else {
                messagesDiv.innerHTML += `<div class="ai-message"><b>AI:</b> Error processing cost estimate.</div>`;
            }
        } else {
            messagesDiv.innerHTML += `<div class="ai-message"><b>AI:</b> Invalid response from server.</div>`;
        }
    } catch (error) {
        messagesDiv.innerHTML += `<div class="ai-message"><b>AI:</b> Request failed.</div>`;
    }

    document.getElementById("userInput").value = "";
    scrollToBottom();  // ⬅️ Auto-scroll after chatbot response
}

// This Function is for Scroll Automatically** ⬇️
function scrollToBottom() {
    let chatbox = document.getElementById("chatbox");
    chatbox.scrollTop = chatbox.scrollHeight;
}