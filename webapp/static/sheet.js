$(document).ready(function() {
    // Handle Tab Switching
    function openTab(evt, tabName) {
        $('.tabcontent').hide();
        $('.tablinks').removeClass('active');
        $('#' + tabName).show();
        $(evt.currentTarget).addClass('active');
    }



    // Add click event listeners to spell cards using event delegation
    $('.spells-container-sheet').on('click', '.spell', function(event) {
     // Close other flipped cards
     $('.spell').not(this).removeClass('flipped');
     // Toggle the clicked card
     $(this).toggleClass('flipped');
     event.stopPropagation();
 
     // Scroll to the card if it's being flipped open
     if ($(this).hasClass('flipped')) {
         $('html, body').animate({
             scrollTop: $(this).offset().top - 100 // Adjust the offset as needed
         }, 500);
     }
    });

    // Close any flipped cards when clicking outside
    $(document).click(function(event) {
        if (!$(event.target).closest('.spell').length) {
            $('.spell').removeClass('flipped');
        }
    });

    // Prevent click events on the spell-back from propagating to the document
    $('.spell-back').click(function(event) {
        event.stopPropagation();
    });

    // Make spells focusable
    $('.spell').attr('tabindex', '0');

    // Add keydown event handler
    $('.spells-container-sheet').on('keydown', '.spell', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
            // Close other flipped cards
            $('.spell').not(this).removeClass('flipped');
            // Toggle the clicked card
            $(this).toggleClass('flipped');
            event.preventDefault();
        }
    });
    // Attach the openTab function to the window so it can be called inline
    window.openTab = openTab;

    // Open the default tab
    $('.tablinks').first().click();
});