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
                if (parsedBody.cost_estimate && Array.isArray(parsedBody.cost_estimate)) {
                    parsedBody.cost_estimate.forEach((estimate, index) => {
                        let formattedResponse = `<div class="ai-message">
                        🤖 <b>AI:</b> <b>Server ${index + 1} Estimate:</b>
                        <div style="margin-top: 10px; margin-bottom: 10px; overflow-x: auto;">
                        <table style="width: 100%; border-collapse: collapse; border: 1px solid #ddd; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #fafafa; box-shadow: 0 0 5px rgba(0,0,0,0.05);">
                        <thead>
                        <tr style="background-color: #f0f0f0; color: #333; font-weight: bold;">
                            <th style="padding: 10px 14px; text-align: left; border: 1px solid #ddd;">Parameter</th>
                            <th style="padding: 10px 14px; text-align: left; border: 1px solid #ddd;">Value</th>
                        </tr>
                        </thead>
                        <tbody>
                        <tr><td style="padding: 10px 14px; border: 1px solid #ddd;">Instance Type</td><td style="padding: 10px 14px; border: 1px solid #ddd;">${estimate.InstanceType}</td></tr>
                        <tr><td style="padding: 10px 14px; border: 1px solid #ddd;">Storage</td><td style="padding: 10px 14px; border: 1px solid #ddd;">${estimate.Storage}</td></tr>
                        <tr><td style="padding: 10px 14px; border: 1px solid #ddd;">Database</td><td style="padding: 10px 14px; border: 1px solid #ddd;">${estimate.Database === "No" ? "No Database" : estimate.Database}</td></tr>
                        <tr><td style="padding: 10px 14px; border: 1px solid #ddd;">Monthly Server Cost</td><td style="padding: 10px 14px; border: 1px solid #ddd;">${estimate["Monthly Server Cost"]}</td></tr>
                        <tr><td style="padding: 10px 14px; border: 1px solid #ddd;">Monthly Storage Cost</td><td style="padding: 10px 14px; border: 1px solid #ddd;">${estimate["Monthly Storage Cost"]}</td></tr>
                        <tr><td style="padding: 10px 14px; border: 1px solid #ddd;">Monthly Database Cost</td><td style="padding: 10px 14px; border: 1px solid #ddd;">${estimate["Monthly Database Cost"]}</td></tr>
                        <tr style="background-color: #e8f5e9; font-weight: bold;">
                            <td style="padding: 10px 14px; border: 1px solid #ddd;">Total Pricing</td>
                            <td style="padding: 10px 14px; border: 1px solid #ddd;">${estimate["Total Pricing"]}</td>
                        </tr>
                        </tbody>
                        </table>
                        </div></div>`;
                
                        messagesDiv.innerHTML += formattedResponse;
                    });
                }                
            } else {
                messagesDiv.innerHTML += `<div class="ai-message">🤖 <b>AI:</b> Error processing cost estimate.</div>`;
            }
        } else {
            messagesDiv.innerHTML += `<div class="ai-message">🤖 <b>AI:</b> Invalid response from server.</div>`;
        }
    } catch (error) {
        messagesDiv.innerHTML += `<div class="ai-message">🤖 <b>AI:</b> Request failed.</div>`;
    }

    document.getElementById("userInput").value = "";
    scrollToBottom();  // Auto-scroll after chatbot response
}

// This Function is for Scroll Automatically** ⬇️
function scrollToBottom() {
    let chatbox = document.getElementById("chatbox");
    chatbox.scrollTop = chatbox.scrollHeight;
}