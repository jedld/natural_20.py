(function(){
  // Simple point-buy system per 5e SRD (8..15 with costs 0,1,2,3,4,5,7)
  const COST = {8:0,9:1,10:2,11:3,12:4,13:5,14:7,15:9};
  const MIN = 8, MAX = 15, BUDGET = 27;
  const abilities = ["str","dex","con","int","wis","cha"];
  let pool = BUDGET;

  function updatePoints() {
    let spent = 0;
    abilities.forEach(ab => {
      const val = parseInt(document.getElementById(`val-${ab}`).innerText, 10);
      spent += COST[val] || 0;
    });
    pool = BUDGET - spent;
    document.getElementById('points-remaining').innerText = pool;
  }

  function setVal(ab, v){
    v = Math.min(MAX, Math.max(MIN, v));
    document.getElementById(`val-${ab}`).innerText = v;
    document.getElementById(`input-${ab}`).value = v;
    updatePoints();
  }

  function adjust(ab, dir){
    const el = document.getElementById(`val-${ab}`);
    const cur = parseInt(el.innerText, 10);
    if(dir>0){
      const next = cur+1;
      const nextCost = COST[next] ?? Infinity;
      const curCost = COST[cur] || 0;
      const delta = nextCost - curCost;
      if(next<=MAX && pool - delta >= 0){ setVal(ab, next); }
    } else {
      const next = cur-1;
      if(next>=MIN){ setVal(ab, next); }
    }
  }

  function getRaces(){
    const el = document.getElementById('races-data');
    if(!el) return {};
    try { return JSON.parse(el.textContent || '{}'); } catch(e){ return {}; }
  }
  function getClasses(){
    const el = document.getElementById('classes-data');
    if(!el) return {};
    try { return JSON.parse(el.textContent || '{}'); } catch(e){ return {}; }
  }

  const RACES = getRaces();
  const CLASSES = getClasses();

  function subracesFor(raceName){
    try{
      const r = RACES[raceName];
      return r && r.subrace ? Object.keys(r.subrace) : [];
    }catch(e){ return []; }
  }

  function roll4d6drop1(){
    const rolls = Array.from({length:4}, ()=> 1+Math.floor(Math.random()*6));
    rolls.sort((a,b)=>a-b);
    return rolls[1]+rolls[2]+rolls[3];
  }

  function setRandom(){
    abilities.forEach(ab=>{
      setVal(ab, roll4d6drop1());
    });
    // Random ignores pointbuy budget label
    document.getElementById('points-remaining').innerText = '-';
  }

  // Wire events
  $(document).on('click', '.inc', function(){ adjust($(this).data('ab'), +1); });
  $(document).on('click', '.dec', function(){ adjust($(this).data('ab'), -1); });

  $("input[name='ability_mode']").on('change', function(){
    const mode = $(this).val();
    if(mode==='random'){
      $('#roll-abilities').show();
    }else{
      $('#roll-abilities').hide();
      // reset to 8s and 27 points
      abilities.forEach(ab=> setVal(ab, 8));
    }
  });

  $('#roll-abilities').on('click', setRandom);

  // Race -> subrace
  $('#race').on('change', function(){
    const val = $(this).val();
    const subs = subracesFor(val);
    const $sub = $('#subrace');
    $sub.empty();
    $sub.append(`<option value="">-- None --</option>`);
    if(subs.length){
      subs.forEach(s=> $sub.append(`<option value="${s}">${s.replace('_',' ')}</option>`));
      $sub.prop('disabled', false);
    } else {
      $sub.prop('disabled', true);
    }
  });

  // ---------- Class & Level dependent options ----------
  function renderClassOptions(){
    const klass = $('#klass').val();
    const level = parseInt($('#level').val()||'1',10);
    const $panel = $('#class-options');
    const $body = $('#class-options-body');
    $body.empty();
    if(!klass || !CLASSES[klass]){
      $panel.hide();
      return;
    }
    const kdata = CLASSES[klass];
    $panel.show();

    // Skills selection
    const skills = kdata.available_skills || [];
    const nSkills = parseInt(kdata.available_skills_choices||0,10);
    if(nSkills>0 && skills.length){
      const gid = 'skills-choices';
      const sWrap = $('<div class="form-group"/>');
      sWrap.append(`<label>Skills: choose ${nSkills}</label>`);
      const row = $('<div class="row"/>');
      skills.forEach((sk, i)=>{
        const col = $('<div class="col-xs-6 col-sm-4 col-md-3"/>');
        const id = `${gid}-${i}`;
        col.append(`
          <div class="checkbox">
            <label>
              <input type="checkbox" class="cb-skill" data-name="${sk}" id="${id}"> ${sk.replace(/_/g,' ')}
            </label>
          </div>`);
        row.append(col);
      });
      sWrap.append(row);
      sWrap.append(`<div class="helper" id="skills-helper">${nSkills} remaining</div>`);
      $body.append(sWrap);

      // limit selection
      $body.on('change', '.cb-skill', function(){
        const selected = $body.find('.cb-skill:checked').length;
        const remaining = Math.max(0, nSkills - selected);
        $('#skills-helper').text(`${remaining} remaining`);
        if(selected >= nSkills){
          $body.find('.cb-skill:not(:checked)').prop('disabled', true);
        } else {
          $body.find('.cb-skill').prop('disabled', false);
        }
      });
    }

    // Simple spell choices for casters (wizard/cleric/bard): level 1-2
    const spellList = kdata.spell_list || {};
    if(spellList && (spellList.cantrip || spellList.level_1)){
      // Decide counts (rough SRD defaults)
      let cantripCount = 0;
      let level1Prep = 0; // prepared/known at start
      let spellbookCount = 0; // wizard spellbook additions
      const klassLower = String(klass).toLowerCase();
      if(klassLower === 'wizard'){
        cantripCount = level===1 ? 3 : 3; // simple rule
        spellbookCount = level===1 ? 6 : 8; // 6 at L1, +2 at L2
        level1Prep = 2; // prepared to start (example minimal)
      } else if(klassLower === 'cleric'){
        cantripCount = level===1 ? 3 : 3; // 3 cantrips at early levels
        level1Prep = level===1 ? 2 : 3; // simple prep guess for early play
      } else if(klassLower === 'bard'){
        cantripCount = level===1 ? 2 : 2;
        level1Prep = level===1 ? 4 : 5; // known spells (approx)
      } else if(klassLower === 'warlock'){
        // Warlocks know a small set of spells; Pact Magic handles slots separately
        const warlockCantrips = [0, 2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4];
        const warlockKnown = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 11, 11, 12, 12, 13, 13, 14, 14, 15, 15];
        const cappedLevel = Math.min(level, warlockCantrips.length - 1);
        cantripCount = warlockCantrips[cappedLevel] || 0;
        // Builder currently offers only 1st-level spells; use known count as cap
        level1Prep = warlockKnown[cappedLevel] || 0;
      }

      const totalCantrips = Array.isArray(spellList.cantrip) ? spellList.cantrip.length : 0;
      if(totalCantrips>0){
        cantripCount = Math.min(cantripCount, totalCantrips);
      }

      if(cantripCount>0 && Array.isArray(spellList.cantrip)){
        const canWrap = $('<div class="form-group"/>');
        canWrap.append(`<label>Cantrips: choose ${cantripCount}</label>`);
        const row = $('<div class="row"/>');
        spellList.cantrip.forEach((sp, i)=>{
          const col = $('<div class="col-xs-6 col-sm-4 col-md-3"/>');
          const id = `cantrip-${i}`;
          col.append(`
            <div class="checkbox">
              <label>
                <input type="checkbox" class="cb-cantrip" data-name="${sp}" id="${id}"> ${sp.replace(/_/g,' ')}
              </label>
            </div>`);
          row.append(col);
        });
        canWrap.append(row);
        canWrap.append(`<div class="helper" id="cantrip-helper">${cantripCount} remaining</div>`);
        $body.append(canWrap);

        $body.on('change', '.cb-cantrip', function(){
          const selected = $body.find('.cb-cantrip:checked').length;
          const remaining = Math.max(0, cantripCount - selected);
          $('#cantrip-helper').text(`${remaining} remaining`);
          if(selected >= cantripCount){
            $body.find('.cb-cantrip:not(:checked)').prop('disabled', true);
          } else {
            $body.find('.cb-cantrip').prop('disabled', false);
          }
        });
      }

      const totalLevel1 = Array.isArray(spellList.level_1) ? spellList.level_1.length : 0;
      if(totalLevel1>0){
        level1Prep = Math.min(level1Prep, totalLevel1);
      }

      if(level1Prep>0 && Array.isArray(spellList.level_1)){
        const sWrap = $('<div class="form-group"/>');
        sWrap.append(`<label>Level 1 Spells: choose ${level1Prep}</label>`);
        const row = $('<div class="row"/>');
        spellList.level_1.forEach((sp, i)=>{
          const col = $('<div class="col-xs-6 col-sm-4 col-md-3"/>');
          const id = `lvl1-${i}`;
          col.append(`
            <div class="checkbox">
              <label>
                <input type="checkbox" class="cb-lvl1" data-name="${sp}" id="${id}"> ${sp.replace(/_/g,' ')}
              </label>
            </div>`);
          row.append(col);
        });
        sWrap.append(row);
        sWrap.append(`<div class="helper" id="lvl1-helper">${level1Prep} remaining</div>`);
        $body.append(sWrap);

        $body.on('change', '.cb-lvl1', function(){
          const selected = $body.find('.cb-lvl1:checked').length;
          const remaining = Math.max(0, level1Prep - selected);
          $('#lvl1-helper').text(`${remaining} remaining`);
          if(selected >= level1Prep){
            $body.find('.cb-lvl1:not(:checked)').prop('disabled', true);
          } else {
            $body.find('.cb-lvl1').prop('disabled', false);
          }
        });
      }

      if(spellbookCount>0 && Array.isArray(spellList.level_1) && klass.toLowerCase()==='wizard'){
        const note = $('<div class="helper"/>').text(`Your spellbook starts with ${spellbookCount} 1st-level spells. We'll seed it from your choices and fill randomly if needed.`);
        $body.append(note);
      }
    }
  }

  $('#klass, #level').on('change', renderClassOptions);
  // initial hide
  $('#class-options').hide();

  $('#cancel-btn').on('click', function(){ window.location.href = '/'; });

  $('#character-form').on('submit', function(e){
    e.preventDefault();
    const formEl = document.getElementById('character-form');
    const fd = new FormData(formEl);
  // append class options
  const skills = [];
  $('#class-options-body .cb-skill:checked').each(function(){ skills.push($(this).data('name')); });
  if(skills.length) fd.append('skills', JSON.stringify(skills));
  const cantrips = [];
  $('#class-options-body .cb-cantrip:checked').each(function(){ cantrips.push($(this).data('name')); });
  if(cantrips.length) fd.append('cantrips', JSON.stringify(cantrips));
  const level1 = [];
  $('#class-options-body .cb-lvl1:checked').each(function(){ level1.push($(this).data('name')); });
  if(level1.length) fd.append('level1_spells', JSON.stringify(level1));
    $.ajax({
      type: 'POST', url: '/create_character', data: fd, dataType: 'json',
      processData: false,
      contentType: false,
      success: function(resp){
        if(resp.error){
          $('#builder-msg').html(`<div class="alert alert-danger">${resp.error}</div>`);
        } else {
          $('#builder-msg').html(`<div class="alert alert-success">Character created!</div>`);
          // If coming from player flow, go to character_selection. Else back home.
          const next = resp.redirect || '/';
          setTimeout(()=> window.location.href = next, 800);
        }
      },
      error: function(){
        $('#builder-msg').html(`<div class="alert alert-danger">Failed to create character.</div>`);
      }
    });
  });

  // init
  updatePoints();
})();
