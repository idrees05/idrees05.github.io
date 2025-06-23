$(document).ready(function () {
    $(window).scroll(function () {
      //  sticky navbar on scroll script  //
      if (this.scrollY > 20) {
        $(".navbar").addClass("sticky");
      } else {
        $(".navbar").removeClass("sticky");
      }
  
      //  scroll-up button show/hide script  //
      if (this.scrollY > 500) {
        $(".scroll-up-btn").addClass("show");
      } else {
        $(".scroll-up-btn").removeClass("show");
      }
    });
  
    //  slide-up script  //
  
    $(".scroll-up-btn").click(function () {
      $("html").animate({ scrollTop: 0 });
      //  removing smooth scroll on slide-up button click  //
      $("html").css("scrollBehavior", "auto");
    });
  
    $(".navbar .menu li a").click(function () {
      //  Smooth scroll on Menu Items click  //
  
      $("html").css("scrollBehavior", "smooth");
    });
  
    //  Toggle Navbar  //
  
    $(".menu-btn").click(function () {
      $(".navbar .menu").toggleClass("active");
      $(".menu-btn i").toggleClass("active");
    });
  
    //  Typing Text Animation  //
  
    var typed = new Typed(".typing", {
      strings: [
        "AI Automation Specialist",
      ],
      typeSpeed: 100,
      backSpeed: 60,
      loop: true
    });
  
    var typed = new Typed(".typing-2", {
      strings: [
        "AI Automation Specialist",
      ],
      typeSpeed: 100,
      backSpeed: 60,
      loop: true
    });
  
    //  Owl Carousel  //
  
    $(".carousel").owlCarousel({
      margin: 20,
      loop: true,
      autoplay: true,
      autoplayTimeOut: 2000,
      autoplayHoverPause: true,
      responsive: {
        0: {
          items: 1,
          nav: false
        },
        600: {
          items: 2,
          nav: false
        },
        1000: {
          items: 3,
          nav: false
        }
      }
    });

    let cvDownloaded = false;

    $('#hireMeLink').click(function(event) {
      event.preventDefault(); // Prevent the default anchor behavior

      // Smooth scroll to the contact section
      const section = document.getElementById('contact');
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });

      // Check if the CV has been downloaded before
      if (!cvDownloaded) {
        setTimeout(() => {
          const link = document.createElement('a');
          link.href = 'ImagesandDocs/Mohammed Idrees Rahman CV.docx'; // The path to the CV file
          link.download = 'Mohammed Idrees Rahman CV.docx'; // Suggested filename for download
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          cvDownloaded = true; // Set the flag so the CV is only downloaded once
        }, 500); // Adjust the delay as needed
      }
    });
  });