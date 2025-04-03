AWS.config.region = "us-east-1"; // Change to your AWS region
AWS.config.credentials = new AWS.CognitoIdentityCredentials({
    IdentityPoolId: "us-east-1:64e5884b-28df-4bbe-ae4e-097bb5132272"
});

const s3 = new AWS.S3();
const BUCKET_NAME = "price-inventory";

// Upload File to S3
function uploadFile() {
    let file = document.getElementById("fileInput").files[0];
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
    
    s3.upload(params, function(err, data) {
        if (err) {
            alert("Upload failed: " + err.message);
        } else {
            document.getElementById("uploadStatus").innerText = "Upload Successful!";
            listFiles(); // Refresh file list
        }
    });
}

// List Files in S3
function listFiles() {
    let params = {
        Bucket: BUCKET_NAME
    };

    s3.listObjects(params, function(err, data) {
        if (err) {
            alert("Error fetching files: " + err.message);
        } else {
            let fileDropdown = document.getElementById("fileDropdown");
            fileDropdown.innerHTML = "";
            // Add default select option
            let defaultOption = document.createElement("option");
            defaultOption.value = "";
            defaultOption.textContent = "Select a file";
            defaultOption.disabled = true;
            defaultOption.selected = true;
            fileDropdown.appendChild(defaultOption);
            data.Contents.forEach(function(file) {
                let option = document.createElement("option");
                option.value = file.Key;
                option.textContent = file.Key;
                fileDropdown.appendChild(option);
            });
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

    let params = {
        Bucket: BUCKET_NAME,
        Key: selectedFile
    };

    s3.getSignedUrl("getObject", params, function(err, url) {
        if (err) {
            alert("Error generating download link: " + err.message);
        } else {
            window.location.href = url;
        }
    });
}

// Load files on page load
window.onload = listFiles;