AWS.config.region = "us-east-1"; // Change to your AWS region
AWS.config.credentials = new AWS.CognitoIdentityCredentials({
    IdentityPoolId: "us-east-1:64e5884b-28df-4bbe-ae4e-097bb5132272"
});

const s3 = new AWS.S3();
const BUCKET_NAME = "price-inventory";
let previousFileList = []; // Store previous file list to track changes
let processingStarted = false; // Flag to track if processing has started
let uploadedFilename = ""; // Used to track original upload
let uploadTime = null; // Track exact upload timestamp

// Upload File to S3
function uploadFile() {
    let fileInput = document.getElementById("fileInput");
    let file = fileInput.files[0];
    if (!file) {
        alert("Please select a file first!");
        return;
    }
    uploadedFilename = file.name; // ✅ Moved after null check
    uploadTime = new Date(); // ✅ Capture upload time

    // Check file type (only allow Excel files)
    const allowedExtensions = ['.xls', '.xlsx', '.xlsm', 'csv'];
    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowedExtensions.includes(fileExtension)) {
        alert("Only Excel files (.xls, .xlsx, .xlsm, csv) are allowed.");
        return;
    }

    // Check file size (limit to 5MB)
    const MAX_SIZE_MB = 5;
    const maxSizeBytes = MAX_SIZE_MB * 1024 * 1024;
    if (file.size > maxSizeBytes) {
        alert("File size exceeds 5 MB. Please upload a smaller file.");
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
            
            // Set "Processing..." after 1 seconds
            setTimeout(() => {
                document.getElementById("uploadStatus").innerText = "Processing...";
                listFiles(); // Refresh file list after processing starts
            }, 1000);
        }
    });
}

// List Files in S3 and detect new files
function listFiles() {
    let params = { Bucket: BUCKET_NAME };
    s3.listObjects(params, function(err, data) {
        if (err) {
            alert("Error fetching files: " + err.message);
            return;
        }

        let fileDropdown = document.getElementById("fileDropdown");
        const currentValue = fileDropdown.value;
        const allFiles = data.Contents.map(file => ({
            key: file.Key,
            lastModified: new Date(file.LastModified)
        }));

        // Step 1: Try to detect uploadedFilename from latest result file
        if (!uploadedFilename) {
            const resultFiles = allFiles.filter(f => f.key.startsWith("Price_"));
            if (resultFiles.length > 0) {
                // Get the most recent result file
                const latestResultFile = resultFiles.sort((a, b) => b.lastModified - a.lastModified)[0];
                const match = latestResultFile.key.match(/^Price_(.+)_\d{8}_\d{6}\.csv$/);
                if (match && match[1]) {
                    uploadedFilename = match[1] + ".xlsx"; // or .csv depending on your format
                }
            }
        }

        let originalNameWithoutExt = uploadedFilename ? uploadedFilename.split('.')[0] : "";

        // Step 2: Get latest result file for this upload
        const resultFilesForThisUpload = allFiles
            .filter(f =>
                f.key.startsWith(`Price_${originalNameWithoutExt}_`) &&
                (!uploadTime || f.lastModified >= uploadTime)
            )
            .sort((a, b) => b.lastModified - a.lastModified);

        const latestResultFile = resultFilesForThisUpload[0];

        // Step 3: Build dropdown list
        let relatedFiles = [];

        if (uploadedFilename) {
            // Add original file if it exists in the bucket
            const originalFile = allFiles.find(f => f.key === uploadedFilename);
            if (originalFile) relatedFiles.push(originalFile.key);
        }

        if (latestResultFile) {
            relatedFiles.push(latestResultFile.key);
        }
        // Remove any accidental duplicates
        relatedFiles = [...new Set(relatedFiles)];

        const newFiles = relatedFiles.filter(file => !previousFileList.includes(file));
        const hasNewFile = newFiles.length > 0;

        // Update dropdown
        fileDropdown.innerHTML = "";
        let defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = "Select a file";
        defaultOption.disabled = true;
        defaultOption.selected = true;
        fileDropdown.appendChild(defaultOption);

        relatedFiles.forEach(fileKey => {
            let option = document.createElement("option");
            option.value = fileKey;
            option.textContent = fileKey;
            fileDropdown.appendChild(option);
        });

        fileDropdown.value = relatedFiles.includes(currentValue) ? currentValue : "";

        if (processingStarted) {
            if (latestResultFile) {
                document.getElementById("uploadStatus").innerText = "Processing Complete!";
                setTimeout(() => {
                    document.getElementById("uploadStatus").innerText = "Now you can download your file from the dropdown";
                    processingStarted = false;
                }, 2000);
            } else {
                document.getElementById("uploadStatus").innerText = "Processing..."; // Keep showing this until result arrives
            }
        }        

        previousFileList = relatedFiles;
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

    // ✅ Clear any previous status messages when user clicks Download
    document.getElementById("uploadStatus").innerText = "";

    let params = {
        Bucket: BUCKET_NAME,
        Key: selectedFile
    };

    s3.getSignedUrl("getObject", params, function(err, url) {
        if (err) {
            alert("Error generating download link: " + err.message);
        } else {
            // ✅ Clear status before triggering download
            document.getElementById("uploadStatus").innerText = "";

            // Initiate the download
            window.location.href = url;

            // ✅ Reset dropdown after 1 second
            setTimeout(() => {
                fileDropdown.value = "";
            }, 1000);

            // ✅ Clear file input field
            document.getElementById("fileInput").value = "";
            uploadedFilename = "";
            uploadTime = null;
        }
    });
}

// **Clear status message when user selects a file from dropdown**
document.getElementById("fileDropdown").addEventListener("change", function () {
    document.getElementById("uploadStatus").innerText = "";
});

window.onload = function () {
    uploadedFilename = ""; // Clear on first load
    listFiles();
    
    // Auto-refresh file list every 5 seconds
    setInterval(listFiles, 5000);
};