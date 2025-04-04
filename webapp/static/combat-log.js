const username = $('body').data('username');
const controls_entities = $('body').data('controls');

// Configure Socket.IO client
const socket = io({
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionAttempts: 5,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
    autoConnect: true,
    path: '/socket.io',
    forceNew: true,
    multiplex: false,
    withCredentials: false
});

socket.on('connect', function () {
    console.log("Connected to the server");
    socket.emit('register', {
        username: username
    });
});

socket.on('connect_error', (error) => {
    console.log('Connection error:', error);
});

socket.on('reconnect_attempt', (attemptNumber) => {
    console.log('Reconnection attempt:', attemptNumber);
});

socket.on('reconnect', () => {
    console.log('Reconnected successfully');
    // Re-register after reconnection
    socket.emit('register', {
        username: username
    });
});

socket.on('disconnect', (reason) => {
    console.log('Disconnected:', reason);
});

socket.on('error', (error) => {
    console.error('Socket error:', error);
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