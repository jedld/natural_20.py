$(document).ready(function() {
    var entityId = $('body').data('id');
    
    // Handle section expansion
    $('.section-header').on('click', function() {
        const section = $(this).closest('.section');
        const content = section.find('.section-content');
        const icon = $(this).find('.toggle-icon');
        
        content.slideToggle(200);
        icon.toggleClass('fa-chevron-down fa-chevron-up');
    });

    // Handle Tab Switching
    function openTab(evt, tabName) {
        $('.tabcontent').hide();
        $('.tablinks').removeClass('active');
        $('#' + tabName).show();
        $(evt.currentTarget).addClass('active');
    }

    function refreshEquipment() {
        $.get('/equipment',
        {
            id: entityId
        },
        function(response) {
            $('.equipment-container').html(response);
        });
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

    $('.equipment-container').on('submit', '.form-unequip', function(event) {
        event.preventDefault();
        var form = $(this);
        var url = form.attr('action');
        var data = form.serialize();
        $.post(url, data, function(response) {
            // Update the spell list
            refreshEquipment();
        });
    });

    $('.equipment-container').on('submit', '.form-equip', function(event) {
        event.preventDefault();
        var form = $(this);
        var url = form.attr('action');
        var data = form.serialize();
        $.post(url, data, function(response) {
            // Update the spell list
            refreshEquipment();
        });
    });

    // Attach the openTab function to the window so it can be called inline
    window.openTab = openTab;

    // Open the default tab
    $('.tablinks').first().click();

    // Controller assignment functionality
    const controllerInput = $('#controller-input');
    const suggestionsList = $('#controller-suggestions');
    const controllersList = $('#controllers-list');
    let currentEntityId = $('body').data('id');

    // Handle input for auto-complete
    controllerInput.on('input', function() {
        const query = $(this).val().trim();
        if (query.length < 2) {
            suggestionsList.hide();
            return;
        }

        // Fetch suggestions from server
        $.get('/get_users', { query: query }, function(users) {
            suggestionsList.empty();
            users.forEach(user => {
                if (!controllersList.find(`li:contains('${user}')`).length) {
                    suggestionsList.append(`<div data-username="${user}">${user}</div>`);
                }
            });
            suggestionsList.show();
        });
    });

    // Handle suggestion selection
    suggestionsList.on('click', 'div', function() {
        const username = $(this).data('username');
        addController(username);
        controllerInput.val('');
        suggestionsList.hide();
    });

    // Handle removing a controller
    controllersList.on('click', '.remove-controller', function() {
        const username = $(this).data('username');
        removeController(username);
    });

    // Add a controller
    function addController(username) {
        $.post('/update_controller', {
            entity_uid: currentEntityId,
            controller: username,
            action: 'add'
        }, function(response) {
            if (response.status === 'ok') {
                controllersList.append(`
                    <li>
                        ${username}
                        <button class="btn btn-sm btn-danger remove-controller" data-username="${username}">×</button>
                    </li>
                `);
            }
        });
    }

    // Remove a controller
    function removeController(username) {
        $.post('/update_controller', {
            entity_uid: currentEntityId,
            controller: username,
            action: 'remove'
        }, function(response) {
            if (response.status === 'ok') {
                controllersList.find(`li:contains('${username}')`).remove();
            }
        });
    }

    // Close suggestions when clicking outside
    $(document).on('click', function(e) {
        if (!$(e.target).closest('.controller-assignment').length) {
            suggestionsList.hide();
        }
    });
});