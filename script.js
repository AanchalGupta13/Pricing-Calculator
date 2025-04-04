AWS.config.region = "us-east-1"; // Change to your AWS region
AWS.config.credentials = new AWS.CognitoIdentityCredentials({
    IdentityPoolId: "us-east-1:64e5884b-28df-4bbe-ae4e-097bb5132272"
});

const s3 = new AWS.S3();
const BUCKET_NAME = "price-inventory";
let previousFileList = []; // Store previous file list to track changes
let processingStarted = false; // Flag to track if processing has started

// Upload File to S3
function uploadFile() {
    let fileInput = document.getElementById("fileInput");
    let file = fileInput.files[0];
    if (!file) {
        alert("Please select a file first!");
        return;
    }

    let params = {
        Bucket: BUCKET_NAME,
        Key: file.name,
        Body: file
    };

    document.getElementById("uploadStatus").innerText = "Uploading...";
    processingStarted = true; // Set processing flag

    s3.upload(params, function(err, data) {
        if (err) {
            alert("Upload failed: " + err.message);
        } else {
            document.getElementById("uploadStatus").innerText = "Upload Successful!";
            
            // Set "Processing..." after 3 seconds
            setTimeout(() => {
                document.getElementById("uploadStatus").innerText = "Processing...";
                listFiles(); // Refresh file list after processing starts
            }, 3000);

            // **Clear file input after upload**
            fileInput.value = ""; 
        }
    });
}

// List Files in S3 and detect new files
function listFiles() {
    let params = { Bucket: BUCKET_NAME };
    s3.listObjects(params, function(err, data) {
        if (err) {
            alert("Error fetching files: " + err.message);
        } else {
            let fileDropdown = document.getElementById("fileDropdown");
            const currentValue = fileDropdown.value; // Store current selection

            // Get latest file list from S3
            const newFileKeys = data.Contents.map(file => file.Key);

            // Detect if a new result file was added
            const newFiles = newFileKeys.filter(file => !previousFileList.includes(file));
            const hasNewFile = newFiles.length > 0;

            // Update the file list in dropdown
            fileDropdown.innerHTML = ""; // Clear existing options

            // Add default option
            let defaultOption = document.createElement("option");
            defaultOption.value = "";
            defaultOption.textContent = "Select a file";
            defaultOption.disabled = true;
            defaultOption.selected = true;
            fileDropdown.appendChild(defaultOption);

            // Add new options
            newFileKeys.forEach(function(fileKey) {
                let option = document.createElement("option");
                option.value = fileKey;
                option.textContent = fileKey;
                fileDropdown.appendChild(option);
            });

            // Restore previous selection if possible
            fileDropdown.value = newFileKeys.includes(currentValue) ? currentValue : "";

            // **Show "Processing Complete!" only if processing was started**
            if (processingStarted && hasNewFile) {
                document.getElementById("uploadStatus").innerText = "Processing Complete!";
                
                // **After 3 seconds, show "Now you can download your file from the dropdown"**
                setTimeout(() => {
                    document.getElementById("uploadStatus").innerText = "Now you can download your file from the dropdown";
                    processingStarted = false; // Reset flag
                }, 3000);
            }

            // Update previous file list
            previousFileList = newFileKeys;
        }
    });
}

// Download Selected File from S3
function downloadSelectedFile() {
    let fileDropdown = document.getElementById("fileDropdown");
    let selectedFile = fileDropdown.value;
    if (!selectedFile) {
        alert("Please select a file to download!");
        return;
    }

    // **Clear status message when file is selected for download**
    document.getElementById("uploadStatus").innerText = "";

    let params = {
        Bucket: BUCKET_NAME,
        Key: selectedFile
    };

    s3.getSignedUrl("getObject", params, function(err, url) {
        if (err) {
            alert("Error generating download link: " + err.message);
        } else {
            window.location.href = url;

            // **Reset dropdown to "Select a file"**
            setTimeout(() => {
                fileDropdown.value = ""; // Reset dropdown
            }, 1000);

            // **Clear the file input field**
            document.getElementById("fileInput").value = "";
        }
    });
}

// **Clear status message when user selects a file from dropdown**
document.getElementById("fileDropdown").addEventListener("change", function () {
    document.getElementById("uploadStatus").innerText = "";
});

window.onload = function () {
    listFiles();
    
    // Auto-refresh file list every 5 seconds
    setInterval(listFiles, 5000);
};