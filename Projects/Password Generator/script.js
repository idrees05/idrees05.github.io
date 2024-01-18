// Select the elements from the DOM
const password = document.getElementById('password');
const generateBtn = document.getElementById('generateBtn');
const copyBtn = document.getElementById('copyBtn');
const feedbackDiv = document.getElementById('feedback'); // A div to show feedback messages to the user

// Constants
const PASSWORD_LENGTH = 12;
const CHARACTERS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()";

// Function to generate a random 12 character password
function generatePassword() {
    let passwordString = "";

    for (let i = 0; i < PASSWORD_LENGTH; i++) {
        let randomNumber = Math.floor(Math.random() * CHARACTERS.length);
        passwordString += CHARACTERS.charAt(randomNumber);
    }

    password.value = passwordString;

    // Display feedback to the user
    showFeedback("Password generated!");
}

// Function to copy the password to the clipboard
function copyPassword() {
    if (password.value) {
        navigator.clipboard.writeText(password.value)
            .then(() => {
                // Inform the user of the password being copied to the clipboard
                showFeedback("Password copied to clipboard!");
            })
            .catch(err => {
                // Handle errors related to clipboard write here, if any
                showFeedback("Failed to copy password!");
            });
    }
}

// Function to show feedback to the user without using alerts
function showFeedback(message) {
    feedbackDiv.innerText = message;

    setTimeout(() => {
        feedbackDiv.innerText = ""; // Clear the feedback after 2 seconds
    }, 2000);
}

// Event listeners
generateBtn.addEventListener('click', generatePassword);
copyBtn.addEventListener('click', copyPassword);
