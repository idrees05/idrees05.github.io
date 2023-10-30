document.getElementById("contact-btn").addEventListener("click", function() {
    // Select the footer element
    var footer = document.querySelector("footer");
  
    // Scroll to the footer
    footer.scrollIntoView({ behavior: "smooth" });
  });

  document.getElementById('viewProjectBtnOne').addEventListener('click', function() {
    window.open("https://github.com/idrees05/idrees05.github.io", "_blank");
});

document.getElementById('viewProjectBtnTwo').addEventListener('click', function() {
    window.open("https://github.com/idrees05/Developer-Training/tree/main/Week%205%20Project/Weather%20Dashboard", "_blank");
});

document.getElementById('viewProjectBtnThree').addEventListener('click', function() {
    window.open("https://github.com/idrees05/Developer-Training/tree/main/Week%205%20Project/To%20do%20List", "_blank");
});
