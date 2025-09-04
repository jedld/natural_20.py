// Simple Web Audio–based SFX engine for spell cues.
// Provides SFX.play(name) and SFX.setVolume(0..1). Uses no external assets.
(function(global){
  let ctx = null;
  let master = null;
  let vol = 0.6; // default master volume
  let unlocked = false;

  function ensureContext(){
    if (!ctx) {
      const AC = global.AudioContext || global.webkitAudioContext;
      if (!AC) return false;
      ctx = new AC();
      master = ctx.createGain();
      master.gain.value = vol;
      master.connect(ctx.destination);
      // Try to unlock on first user gesture
      const unlock = () => {
        if (!ctx) return;
        if (ctx.state === 'suspended') ctx.resume().catch(()=>{});
        unlocked = true;
        global.removeEventListener('click', unlock);
        global.removeEventListener('touchstart', unlock);
        global.removeEventListener('keydown', unlock);
      };
      global.addEventListener('click', unlock, { once: true });
      global.addEventListener('touchstart', unlock, { once: true });
      global.addEventListener('keydown', unlock, { once: true });
    }
    if (ctx && ctx.state === 'suspended') ctx.resume().catch(()=>{});
    return !!ctx;
  }

  function setVolume(v){ vol = Math.max(0, Math.min(1, v)); if (master) master.gain.value = vol; }

  // Helpers
  function envGain(t0, attack, hold, release, peak=1){
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0001, peak), t0 + attack);
    g.gain.setValueAtTime(Math.max(0.0001, peak), t0 + attack + hold);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + attack + hold + release);
    return g;
  }
  function osc(type, freq){ const o = ctx.createOscillator(); o.type = type; o.frequency.value = freq; return o; }
  function noiseBuffer(){
    const len = ctx.sampleRate * 1.5; const buffer = ctx.createBuffer(1, len, ctx.sampleRate); const data = buffer.getChannelData(0);
    for (let i=0;i<len;i++){ data[i] = (Math.random()*2 - 1) * 0.5; }
    return buffer;
  }
  function playNoise(t0, dur, {type='white', band=[200,4000]}={}){
    const src = ctx.createBufferSource(); src.buffer = noiseBuffer();
    let node = src;
    // bandpass
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass'; bp.frequency.value = (band[0] + band[1]) / 2; bp.Q.value = 0.9;
    node.connect(bp); node = bp;
    const g = envGain(t0, 0.01, Math.max(0,dur-0.05), 0.2, 0.7);
    node.connect(g); g.connect(master);
    src.start(t0); src.stop(t0 + dur + 0.3);
  }
  // Flamethrower-style whoosh: layered filtered noise with ignition burst
  function flameWhoosh(t0, dur=0.5, power=1){
    // High hiss
    const nHi = ctx.createBufferSource(); nHi.buffer = noiseBuffer();
    const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 1000; hp.Q.value = 0.7;
    const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 2500; bp.Q.value = 0.9;
    const gHi = envGain(t0, 0.006, Math.max(0,dur-0.08), 0.12, 0.95*power);
    nHi.connect(hp); hp.connect(bp); bp.connect(gHi); gHi.connect(master);
    nHi.start(t0); nHi.stop(t0 + dur + 0.2);

    // Low rumble
    const nLo = ctx.createBufferSource(); nLo.buffer = noiseBuffer();
    const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 550; lp.Q.value = 0.6;
    const gLo = envGain(t0, 0.015, Math.max(0,dur-0.1), 0.22, 0.6*power);
    nLo.connect(lp); lp.connect(gLo); gLo.connect(master);
    nLo.start(t0); nLo.stop(t0 + dur + 0.3);

    // Ignition burst (bright snap)
    const ign = ctx.createBufferSource(); ign.buffer = noiseBuffer();
    const ignHp = ctx.createBiquadFilter(); ignHp.type = 'highpass'; ignHp.frequency.value = 2000; ignHp.Q.value = 0.8;
    const ignG = envGain(t0, 0.004, 0.05, 0.08, 1.0*power);
    ign.connect(ignHp); ignHp.connect(ignG); ignG.connect(master);
    ign.start(t0); ign.stop(t0 + 0.2);
  }
  function glide(t0, startF, endF, dur, type='sine', peak=0.9){
    const o = osc(type, startF);
    const g = envGain(t0, 0.02, Math.max(0,dur-0.04), 0.1, peak);
    o.connect(g); g.connect(master);
    o.frequency.setValueAtTime(startF, t0);
    o.frequency.exponentialRampToValueAtTime(endF, t0 + dur);
    o.start(t0); o.stop(t0 + dur + 0.2);
  }
  function chord(t0, freqs, dur, type='sine', peak=0.6){
    const g = envGain(t0, 0.02, Math.max(0,dur-0.05), 0.2, peak);
    g.connect(master);
    freqs.forEach(f=>{ const o = osc(type, f); o.connect(g); o.start(t0); o.stop(t0 + dur + 0.3); });
  }

  // Named cues
  function play(name){
    if (!ensureContext()) return;
    const t0 = ctx.currentTime + 0.01;
    try {
      switch(String(name)){
        case 'bless_cast':
          chord(t0, [660, 990, 1320], 0.5, 'sine', 0.4);
          break;
        case 'chill_touch_cast':
          // eerie spectral swell
          glide(t0, 660, 440, 0.22, 'sine', 0.35);
          playNoise(t0, 0.25, { band: [700, 2000] });
          break;
        case 'chill_touch_grab':
          // cold snap + low hum
          chord(t0, [196, 261.6], 0.25, 'triangle', 0.5);
          glide(t0+0.05, 220, 180, 0.2, 'sine', 0.25);
          break;
        case 'guiding_bolt_charge':
          glide(t0, 220, 880, 0.18, 'sine', 0.5);
          break;
        case 'guiding_bolt_impact':
          chord(t0, [880, 1320, 1760], 0.6, 'triangle', 0.7);
          break;
        case 'sacred_flame_start':
          playNoise(t0, 0.35, { band: [600, 4000] }); glide(t0, 880, 660, 0.25, 'sine', 0.3);
          break;
        case 'sacred_flame_impact':
          chord(t0, [990, 1485, 1980], 0.5, 'sine', 0.5);
          break;
        case 'magic_missile_fire':
          glide(t0, 660, 1320, 0.12, 'square', 0.5);
          break;
        case 'magic_missile_impact':
          chord(t0, [1320], 0.2, 'triangle', 0.5);
          break;
        case 'firebolt_fire':
          playNoise(t0, 0.2, { band: [800, 2500] }); glide(t0, 330, 660, 0.08, 'sawtooth', 0.4);
          break;
        case 'firebolt_impact':
          playNoise(t0, 0.15, { band: [1200, 3000] });
          break;
        case 'ray_of_frost_fire':
          glide(t0, 990, 660, 0.16, 'sine', 0.4); chord(t0+0.05, [1320], 0.25, 'sine', 0.25);
          break;
        case 'ray_of_frost_impact':
          chord(t0, [880, 1175, 1568], 0.5, 'sine', 0.5);
          break;
        case 'burning_hands_cast':
          flameWhoosh(t0, 0.6, 1.0);
          break;
        case 'shield_of_faith_start':
          chord(t0, [440, 660, 880], 0.8, 'triangle', 0.35);
          break;
        case 'healing_word_cast':
          chord(t0, [523.25, 659.25, 783.99], 0.7, 'sine', 0.45); // C5-E5-G5
          break;
        case 'cure_wounds_cast':
          chord(t0, [392, 523.25, 659.25], 0.5, 'sine', 0.45); // G4-C5-E5
          break;
        case 'cure_wounds_bloom':
          chord(t0, [659.25, 880], 0.6, 'triangle', 0.5);
          break;
        case 'inflict_wounds_cast':
          glide(t0, 180, 120, 0.25, 'sine', 0.5); playNoise(t0, 0.22, { band: [200, 1200] });
          break;
        case 'inflict_wounds_impact':
          chord(t0, [110, 220], 0.4, 'triangle', 0.6);
          break;
        case 'ice_knife_throw':
          glide(t0, 1320, 880, 0.18, 'sine', 0.35);
          break;
        case 'ice_knife_shatter':
          chord(t0, [1568, 2093], 0.4, 'sine', 0.5); playNoise(t0, 0.25, { band: [1500, 5000] });
          break;
        // --- Distinct Attack cues ---
        case 'attack_arrow': // bow twang + whoosh
          glide(t0, 440, 660, 0.08, 'triangle', 0.35);
          playNoise(t0, 0.12, { band: [1200, 3500] });
          break;
        case 'attack_bolt': // heavier crossbow thunk
          glide(t0, 220, 330, 0.06, 'square', 0.4);
          playNoise(t0, 0.1, { band: [800, 2500] });
          break;
        case 'attack_thrown': // light whoosh spin
          playNoise(t0, 0.18, { band: [900, 2600] });
          break;
        case 'attack_slash': // blade swish
          glide(t0, 520, 880, 0.09, 'sine', 0.4);
          break;
        case 'attack_blunt': // thud
          chord(t0, [196, 261.6], 0.12, 'triangle', 0.5);
          playNoise(t0, 0.08, { band: [200, 900] });
          break;
        case 'attack_thrust': // stab ping
          glide(t0, 660, 990, 0.06, 'sine', 0.45);
          break;
        case 'attack_bite': // chomp (double transient)
          chord(t0, [330], 0.06, 'square', 0.5);
          chord(t0 + 0.07, [247], 0.06, 'square', 0.5);
          break;
        case 'attack_claw': // scratch
          playNoise(t0, 0.12, { band: [1500, 4500] });
          break;
        case 'attack_generic_melee':
          glide(t0, 480, 720, 0.07, 'sine', 0.35);
          break;
        case 'attack_generic_ranged':
          playNoise(t0, 0.12, { band: [1000, 3000] });
          break;
        case 'attack_impact_melee':
          chord(t0, [392, 523.25], 0.18, 'triangle', 0.55);
          break;
        case 'attack_impact_ranged':
          chord(t0, [880], 0.12, 'sine', 0.45);
          break;
        default:
          // Unknown cue: do nothing
          break;
      }
    } catch (e) { /* no-op */ }
  }

  global.SFX = { play, setVolume };
})(window);
