$(document).ready(function () {
    var entityId = $('body').data('id');

    // Handle section expansion
    $('.section-header').on('click', function () {
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
            function (response) {
                $('.equipment-container').html(response);
            });
    }


    // Add click event listeners to spell cards using event delegation
    $('.spells-container-sheet').on('click', '.spell', function (event) {
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
    $(document).click(function (event) {
        if (!$(event.target).closest('.spell').length) {
            $('.spell').removeClass('flipped');
        }
    });

    // Prevent click events on the spell-back from propagating to the document
    $('.spell-back').click(function (event) {
        event.stopPropagation();
    });

    // Make spells focusable
    $('.spell').attr('tabindex', '0');

    // Add keydown event handler
    $('.spells-container-sheet').on('keydown', '.spell', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
            // Close other flipped cards
            $('.spell').not(this).removeClass('flipped');
            // Toggle the clicked card
            $(this).toggleClass('flipped');
            event.preventDefault();
        }
    });

    $('.equipment-container').on('submit', '.form-unequip', function (event) {
        event.preventDefault();
        var form = $(this);
        var url = form.attr('action');
        var data = form.serialize();
        $.post(url, data, function (response) {
            // Update the spell list
            refreshEquipment();
        });
    });

    $('.equipment-container').on('submit', '.form-equip', function (event) {
        event.preventDefault();
        var form = $(this);
        var url = form.attr('action');
        var data = form.serialize();
        $.post(url, data, function (response) {
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
    const controllerSelect = $('#controller-select');
    const suggestionsList = $('#controller-suggestions');
    const controllersList = $('#controllers-list');
    let currentEntityId = $('body').data('id');

    // Handle controller select dropdown
    controllerSelect.on('change', function () {
        const username = $(this).val();
        if (username) {
            addController(username);
            $(this).val(''); // Reset dropdown
        }
    });

    // Handle input for auto-complete
    controllerInput.on('input', function () {
        const query = $(this).val().trim();
        if (query.length < 2) {
            suggestionsList.hide();
            return;
        }

        // Fetch suggestions from server
        $.get('/get_users', { query: query }, function (users) {
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
    suggestionsList.on('click', 'div', function () {
        const username = $(this).data('username');
        addController(username);
        controllerInput.val('');
        suggestionsList.hide();
    });

    // Handle removing a controller
    controllersList.on('click', '.remove-controller', function () {
        const username = $(this).data('username');
        removeController(username);
    });

    // Add a controller
    function addController(username) {
        $.post('/update_controller', {
            entity_uid: currentEntityId,
            controller: username,
            action: 'add'
        }, function (response) {
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
        }, function (response) {
            if (response.status === 'ok') {
                controllersList.find(`li:contains('${username}')`).remove();
            }
        });
    }

    // Close suggestions when clicking outside
    $(document).on('click', function (e) {
        if (!$(e.target).closest('.controller-assignment').length) {
            suggestionsList.hide();
        }
    });

    // Container Management Functionality
    
    // Load items catalog for autocomplete
    $.get('/dm/items_catalog', function(data) {
        const datalist = $('#items-catalog');
        if (data.success && data.items) {
            data.items.forEach(item => {
                datalist.append(`<option value="${item.name}"></option>`);
            });
        }
    });

    // Toggle container contents view
    $('.equipment-container').on('click', '.container-toggle-btn', function(e) {
        e.preventDefault();
        const entityUid = $(this).data('entity');
        const containerName = $(this).data('container');
        const containerId = containerName.replace(/\s+/g, '-');
        
        // Fetch container contents
        $.get('/dm/container/contents', {
            entity_id: entityUid,
            container_name: containerName
        }, function(response) {
            if (response.success) {
                const containerDiv = $(`#container-${containerId}`);
                const itemsList = containerDiv.find('.container-items-list');
                
                // Clear loading message
                itemsList.empty();
                
                if (response.contents.length === 0) {
                    itemsList.append('<li class="container-empty">Container is empty</li>');
                } else {
                    response.contents.forEach(content => {
                        itemsList.append(`
                            <li class="container-item" data-item-name="${content.type}">
                                <span class="container-item-name">${content.type}</span>
                                <span class="container-item-qty">x${content.qty || 1}</span>
                                <button class="btn btn-sm btn-danger remove-container-item"
                                        data-entity="${entityUid}"
                                        data-container="${containerName}"
                                        data-item="${content.type}">
                                    Remove
                                </button>
                            </li>
                        `);
                    });
                }
                
                // Show container contents
                containerDiv.slideDown(200);
                $(this).text('Hide Contents');
            } else {
                alert('Failed to load container contents: ' + response.error);
            }
        }).fail(function() {
            alert('Error loading container contents');
        });
    });

    // Close container contents view
    $('.equipment-container').on('click', '.container-close-btn', function(e) {
        e.preventDefault();
        const containerId = $(this).data('container');
        $(`#container-${containerId}`).slideUp(200);
        $(`.container-toggle-btn[data-container="${containerId.replace(/-/g, ' ')}"]`).text('View Contents');
    });

    // Open add item modal
    $('.equipment-container').on('click', '.container-add-btn', function(e) {
        e.preventDefault();
        const entityUid = $(this).data('entity');
        const containerName = $(this).data('container');
        
        $('#modal-entity-id').val(entityUid);
        $('#modal-container-name').val(containerName);
        $('#container-modal-title').text(`Add Item to ${containerName}`);
        $('#container-modal').fadeIn(200);
    });

    // Close modal
    $('.modal-close').on('click', function() {
        $('#container-modal').fadeOut(200);
    });

    // Handle add item form submission
    $('#container-add-form').on('submit', function(e) {
        e.preventDefault();
        const formData = $(this).serialize();
        
        $.post('/dm/container/add', formData, function(response) {
            if (response.success) {
                // Close modal
                $('#container-modal').fadeOut(200);
                
                // Reset form
                $('#modal-item-name').val('');
                $('#modal-item-qty').val('1');
                
                // Refresh container contents
                const containerName = $('#modal-container-name').val();
                const entityUid = $('#modal-entity-id').val();
                const containerId = containerName.replace(/\s+/g, '-');
                
                $.get('/dm/container/contents', {
                    entity_id: entityUid,
                    container_name: containerName
                }, function(resp) {
                    if (resp.success) {
                        const containerDiv = $(`#container-${containerId}`);
                        const itemsList = containerDiv.find('.container-items-list');
                        
                        itemsList.empty();
                        
                        if (resp.contents.length === 0) {
                            itemsList.append('<li class="container-empty">Container is empty</li>');
                        } else {
                            resp.contents.forEach(content => {
                                itemsList.append(`
                                    <li class="container-item" data-item-name="${content.type}">
                                        <span class="container-item-name">${content.type}</span>
                                        <span class="container-item-qty">x${content.qty || 1}</span>
                                        <button class="btn btn-sm btn-danger remove-container-item"
                                                data-entity="${entityUid}"
                                                data-container="${containerName}"
                                                data-item="${content.type}">
                                            Remove
                                        </button>
                                    </li>
                                `);
                            });
                        }
                    }
                });
            } else {
                alert('Failed to add item: ' + response.error);
            }
        }).fail(function() {
            alert('Error adding item to container');
        });
    });

    // Remove item from container
    $('.equipment-container').on('click', '.remove-container-item', function(e) {
        e.preventDefault();
        const entityUid = $(this).data('entity');
        const containerName = $(this).data('container');
        const itemName = $(this).data('item');
        
        if (confirm(`Remove ${itemName} from ${containerName}?`)) {
            $.post('/dm/container/remove', {
                entity_id: entityUid,
                container_name: containerName,
                item_name: itemName,
                qty: 1
            }, function(response) {
                if (response.success) {
                    // Refresh container contents
                    const containerId = containerName.replace(/\s+/g, '-');
                    
                    $.get('/dm/container/contents', {
                        entity_id: entityUid,
                        container_name: containerName
                    }, function(resp) {
                        if (resp.success) {
                            const containerDiv = $(`#container-${containerId}`);
                            const itemsList = containerDiv.find('.container-items-list');
                            
                            itemsList.empty();
                            
                            if (resp.contents.length === 0) {
                                itemsList.append('<li class="container-empty">Container is empty</li>');
                            } else {
                                resp.contents.forEach(content => {
                                    itemsList.append(`
                                        <li class="container-item" data-item-name="${content.type}">
                                            <span class="container-item-name">${content.type}</span>
                                            <span class="container-item-qty">x${content.qty || 1}</span>
                                            <button class="btn btn-sm btn-danger remove-container-item"
                                                    data-entity="${entityUid}"
                                                    data-container="${containerName}"
                                                    data-item="${content.type}">
                                                Remove
                                            </button>
                                        </li>
                                    `);
                                });
                            }
                        }
                    });
                } else {
                    alert('Failed to remove item: ' + response.error);
                }
            }).fail(function() {
                alert('Error removing item from container');
            });
        }
    });
});