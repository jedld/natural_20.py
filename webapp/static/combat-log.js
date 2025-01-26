const username = $('body').data('username');
const controls_entities = $('body').data('controls');
const socket = io();

socket.on('connect', function () {
    console.log("Connected to the server");
    socket.emit('register', {
        username: username
    });
});

socket.on('message', function (data) {
    console.log('Message received:', data);
    switch (data.type) {
        case 'console':
            var console_message = data.message;
            $('.container #console').append('<p>' + console_message + '</p>');
            break;
    }
});