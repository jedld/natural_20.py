const Effects = {
  createRainEffect: function () {
    // Set up variables
    var canvas = document.querySelector('canvas');
    var ctx = canvas.getContext('2d');
    var w = canvas.width;
    var h = canvas.height;
    var drops = [];

    // Create drop object
    function Drop() {
      this.x = Math.random() * w;
      this.y = Math.random() * h;
      this.r = Math.random() * 1 + 0.5; // thinner lines
      this.speed = 10 + Math.random() * 10 + 1;
      this.angle = Math.random() * 5;
    }

    // Create drops
    for (var i = 0; i < 100; i++) {
      drops.push(new Drop());
    }

    // Draw drops
    function draw() {
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#fff';
      ctx.beginPath();
      for (var i = 0; i < drops.length; i++) {
        var drop = drops[i];
        ctx.moveTo(drop.x, drop.y);
        ctx.lineTo(drop.x + drop.angle, drop.y + drop.speed + 3);
        ctx.lineWidth = drop.r;
        ctx.strokeStyle = '#fff';
        ctx.stroke();
      }
      move();
    }

    // Move drops
    function move() {
      for (var i = 0; i < drops.length; i++) {
        var drop = drops[i];
        drop.y += drop.speed;
        drop.x += drop.angle / 10;
        if (drop.y > h) {
          drop.y = -25;
        }
        if (drop.x > w) {
          drop.x = 0;
        }
      }
    }

    // Start animation loop
    var interval = setInterval(draw, 33);

    // Stop rain effect
    function stopRainEffect() {
      clearInterval(interval);
      ctx.clearRect(0, 0, w, h);
    }

    return {
      stopRainEffect: stopRainEffect
    };
  },
  
  createSnowEffect: function () {
    // Set up variables
    var canvas = document.querySelector('canvas');
    var ctx = canvas.getContext('2d');
    var w = canvas.width;
    var h = canvas.height;
    var flakes = [];

    // Create flake object
    function Flake() {
      this.x = Math.random() * w;
      this.y = Math.random() * h;
      this.r = Math.random() * 4 + 1; // thicker lines
      this.speed = Math.random() * 3 + 1;
      this.angle = Math.random() * 360;
    }

    // Create flakes
    for (var i = 0; i < 100; i++) {
      flakes.push(new Flake());
    }

    // Draw flakes
    function draw() {
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#fff';
      ctx.beginPath();
      for (var i = 0; i < flakes.length; i++) {
        var flake = flakes[i];
        ctx.moveTo(flake.x, flake.y);
        ctx.arc(flake.x, flake.y, flake.r, 0, Math.PI * 2, true);
      }
      ctx.fill();
      move();
    }

    // Move flakes
    function move() {
      for (var i = 0; i < flakes.length; i++) {
        var flake = flakes[i];
        flake.y += flake.speed;
        flake.x += Math.cos(flake.angle) * 2;
        if (flake.y > h) {
          flake.y = -25;
        }
        if (flake.x > w) {
          flake.x = 0;
        }
        if (flake.x < 0) {
          flake.x = w;
        }
      }
    }

    // Start animation loop
    var interval = setInterval(draw, 33);

    // Stop snow effect
    function stopSnowEffect() {
      clearInterval(interval);
      ctx.clearRect(0, 0, w, h);
    }

    return {
      stopSnowEffect: stopSnowEffect
    };
  }
}
