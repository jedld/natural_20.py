(function(){
  // Simple point-buy system per 5e SRD (8..15 with costs 0,1,2,3,4,5,7)
  const COST = {8:0,9:1,10:2,11:3,12:4,13:5,14:7,15:9};
  const MIN = 8, MAX = 15, BUDGET = 27;
  const abilities = ["str","dex","con","int","wis","cha"];
  const abilityLabels = { str: 'Strength', dex: 'Dexterity', con: 'Constitution', int: 'Intelligence', wis: 'Wisdom', cha: 'Charisma' };
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
  const formEl = document.getElementById('character-form');
  const editMode = (formEl && formEl.dataset && formEl.dataset.editMode === 'true');
  function getEditCharacter(){
    const el = document.getElementById('edit-character-data');
    if(!el) return null;
    try { return JSON.parse(el.textContent || '{}'); } catch(e){ return null; }
  }
  const EDIT_CHARACTER = getEditCharacter();

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
    $body.off();
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

    function abilityMod(score){
      const n = parseInt(score || '10', 10);
      return Math.floor((n - 10) / 2);
    }

    function classSpellCaps(klassName, levelNum, klassData){
      const key = String(klassName || '').toLowerCase();
      // Includes newly added core classes so builder/editor stays in sync.
      const tables = {
        wizard: [[3,2],[3,3],[3,4,2],[4,4,3]],
        cleric: [[3,2],[3,3],[3,4,2],[4,4,3]],
        druid: [[2,2],[2,3],[2,4,2],[3,4,3]],
        bard: [[2,2],[2,3],[2,4,2],[3,4,3]],
        warlock: [[2,1],[2,2],[2,0,2],[3,0,2]],
        sorcerer: [[4,2],[4,3],[4,4,2],[5,4,3]],
        paladin: [[0,0],[0,2],[0,3],[0,3]],
        ranger: [[0,0],[0,2],[0,3],[0,3]]
      };
      const row = (tables[key] && tables[key][Math.max(1, levelNum) - 1]) || [];
      let cantripCap = parseInt(row[0] || 0, 10) || 0;
      let level1Cap = parseInt(row[1] || 0, 10) || 0;

      if(key === 'wizard'){
        level1Cap = Math.max(level1Cap, Math.max(1, levelNum + abilityMod($('#input-int').val())));
      } else if(key === 'cleric' || key === 'druid' || key === 'paladin'){
        const spellAbility = String((klassData && klassData.spellcasting_ability) || (key === 'paladin' ? 'charisma' : 'wisdom')).toLowerCase();
        const short = spellAbility.substring(0,3);
        level1Cap = Math.max(level1Cap, Math.max(1, levelNum + abilityMod($(`#input-${short}`).val())));
      } else if(key === 'bard'){
        const known = [0,4,5,6,7,8,9,10,11,12,14,15,15,16,18,19,19,20,22,22,22];
        level1Cap = Math.max(level1Cap, known[Math.min(levelNum, known.length - 1)] || 0);
      } else if(key === 'warlock'){
        const known = [0,2,3,4,5,6,7,8,9,10,10,11,11,12,12,13,13,14,14,15,15];
        level1Cap = Math.max(level1Cap, known[Math.min(levelNum, known.length - 1)] || 0);
      } else if(key === 'sorcerer'){
        const known = [0,2,3,4,5,6,7,8,9,10,11,12,12,13,13,14,14,15,15,15,15];
        level1Cap = Math.max(level1Cap, known[Math.min(levelNum, known.length - 1)] || 0);
      } else if(key === 'ranger'){
        const known = [0,0,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11];
        level1Cap = Math.max(level1Cap, known[Math.min(levelNum, known.length - 1)] || 0);
      }

      const spellbookCap = key === 'wizard' ? (6 + (Math.max(1, levelNum) - 1) * 2) : 0;
      return { cantripCap, level1Cap, spellbookCap };
    }

    // Spell choices for classes with spell lists.
    const spellList = kdata.spell_list || {};
    if(spellList && (spellList.cantrip || spellList.level_1)){
      const caps = classSpellCaps(klass, level, kdata);
      let cantripCount = caps.cantripCap;
      let level1Prep = caps.level1Cap;
      let spellbookCount = caps.spellbookCap;

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

    const featOptions = kdata.feat_choices || kdata.available_feats || [];
    const featCount = parseInt(kdata.feat_choices_count || kdata.available_feats_choices || 0, 10) || 0;
    if(Array.isArray(featOptions) && featOptions.length){
      const wrap = $('<div class="form-group"/>');
      wrap.append(`<label>Feats${featCount > 0 ? `: choose ${featCount}` : ''}</label>`);
      const row = $('<div class="row"/>');
      featOptions.forEach((feat, idx)=>{
        const col = $('<div class="col-xs-6 col-sm-4 col-md-3"/>');
        const id = `feat-${idx}`;
        col.append(`
          <div class="checkbox">
            <label>
              <input type="checkbox" class="cb-feat" data-name="${feat}" id="${id}"> ${feat.replace(/_/g,' ')}
            </label>
          </div>`);
        row.append(col);
      });
      wrap.append(row);
      if(featCount > 0){
        wrap.append(`<div class="helper" id="feat-helper">${featCount} remaining</div>`);
      }
      $body.append(wrap);

      $body.on('change', '.cb-feat', function(){
        if(featCount <= 0) return;
        const selected = $body.find('.cb-feat:checked').length;
        const remaining = Math.max(0, featCount - selected);
        $('#feat-helper').text(`${remaining} remaining`);
        if(selected >= featCount){
          $body.find('.cb-feat:not(:checked)').prop('disabled', true);
        } else {
          $body.find('.cb-feat').prop('disabled', false);
        }
      });
    }
  }

  function renderRaceOptions(){
    const race = $('#race').val();
    const subrace = $('#subrace').val();
    const $panel = $('#race-options');
    const $body = $('#race-options-body');
    $body.empty();
    $body.off();
    if(!race || !RACES[race]){
      $panel.hide();
      return;
    }

    const base = RACES[race] || {};
    const sub = (base.subrace && subrace && base.subrace[subrace]) || {};
    let hasOptions = false;

    const flex = sub.flexible_ability || base.flexible_ability;
    if(flex && Array.isArray(flex.picks) && flex.picks.length){
      const picks = flex.picks;
      const unique = flex.unique !== false;
      const wrap = $('<div class="form-group"/>');
      wrap.append('<label>Ability Score Increases</label>');
      picks.forEach((pick, idx)=>{
        const amount = parseInt(pick.amount, 10) || 1;
        const selectId = `race-ability-${idx}`;
        const row = $('<div style="margin-bottom:8px;"/>');
        const select = $(`<select class="form-control race-ability-pick" data-amount="${amount}" id="${selectId}" required></select>`);
        select.append('<option value="">-- Choose Ability --</option>');
        abilities.forEach(ab=>{
          const label = abilityLabels[ab] || ab.toUpperCase();
          select.append(`<option value="${ab}">${label} (+${amount})</option>`);
        });
        row.append(select);
        wrap.append(row);
      });
      const helperText = unique && flex.picks.length > 1
        ? 'Choose different abilities for each bonus.'
        : 'Select abilities to receive these bonuses.';
      wrap.append(`<div class="helper">${helperText}</div>`);
      $body.append(wrap);

      const enforceUnique = ()=>{
        if(!unique){ return; }
        const selected = {};
        $body.find('.race-ability-pick').each(function(){
          const val = $(this).val();
          if(val){ selected[val] = true; }
        });
        $body.find('.race-ability-pick').each(function(){
          const current = $(this).val();
          $(this).find('option').each(function(){
            const optVal = $(this).attr('value');
            if(!optVal){ return; }
            const disable = selected[optVal] && optVal !== current;
            $(this).prop('disabled', disable);
          });
        });
      };
      $body.on('change', '.race-ability-pick', enforceUnique);
      enforceUnique();
      hasOptions = true;
    }

    const skillChoices = sub.skill_choices || base.skill_choices;
    if(skillChoices && skillChoices.count){
      const count = parseInt(skillChoices.count, 10) || 0;
      const options = skillChoices.options || [];
      if(count > 0 && options.length){
        const wrap = $('<div class="form-group"/>');
        wrap.append(`<label>Racial Skill Proficiency: choose ${count}</label>`);
        const row = $('<div class="row"/>');
        options.forEach((skill, idx)=>{
          const col = $('<div class="col-xs-6 col-sm-4 col-md-3"/>');
          const id = `race-skill-${idx}`;
          col.append(`
            <div class="checkbox">
              <label>
                <input type="checkbox" class="cb-race-skill" data-name="${skill}" id="${id}"> ${skill.replace(/_/g,' ')}
              </label>
            </div>`);
          row.append(col);
        });
        wrap.append(row);
        wrap.append(`<div class="helper" id="race-skill-helper">${count} remaining</div>`);
        $body.append(wrap);

        const updateSkillHelper = ()=>{
          const selected = $body.find('.cb-race-skill:checked').length;
          const remaining = Math.max(0, count - selected);
          $('#race-skill-helper').text(`${remaining} remaining`);
          if(selected >= count){
            $body.find('.cb-race-skill:not(:checked)').prop('disabled', true);
          } else {
            $body.find('.cb-race-skill').prop('disabled', false);
          }
        };
        $body.on('change', '.cb-race-skill', updateSkillHelper);
        updateSkillHelper();
        hasOptions = true;
      }
    }

    const languageChoices = sub.language_choices || base.language_choices;
    if(languageChoices && languageChoices.count){
      const count = parseInt(languageChoices.count, 10) || 0;
      const options = languageChoices.options || [];
      if(count > 0 && options.length){
        const wrap = $('<div class="form-group"/>');
        wrap.append(`<label>Bonus Languages: choose ${count}</label>`);
        const row = $('<div class="row"/>');
        options.forEach((lang, idx)=>{
          const col = $('<div class="col-xs-6 col-sm-4 col-md-3"/>');
          const id = `race-language-${idx}`;
          col.append(`
            <div class="checkbox">
              <label>
                <input type="checkbox" class="cb-race-language" data-name="${lang}" id="${id}"> ${lang.replace(/_/g,' ')}
              </label>
            </div>`);
          row.append(col);
        });
        wrap.append(row);
        wrap.append(`<div class="helper" id="race-language-helper">${count} remaining</div>`);
        $body.append(wrap);

        const updateLanguageHelper = ()=>{
          const selected = $body.find('.cb-race-language:checked').length;
          const remaining = Math.max(0, count - selected);
          $('#race-language-helper').text(`${remaining} remaining`);
          if(selected >= count){
            $body.find('.cb-race-language:not(:checked)').prop('disabled', true);
          } else {
            $body.find('.cb-race-language').prop('disabled', false);
          }
        };
        $body.on('change', '.cb-race-language', updateLanguageHelper);
        updateLanguageHelper();
        hasOptions = true;
      }
    }

    if(hasOptions){
      $panel.show();
    } else {
      $panel.hide();
    }
  }

  $('#klass, #level').on('change', renderClassOptions);
  $('#race, #subrace').on('change', renderRaceOptions);
  // initial hide
  $('#class-options').hide();
  $('#race-options').hide();

  $('#cancel-btn').on('click', function(){
    const url = $('#cancel-btn').data('cancel-url') || '/';
    window.location.href = url;
  });

  $('#character-form').on('submit', function(e){
    e.preventDefault();
    $('#builder-msg').empty();
    const raceVal = $('#race').val();
    const subraceVal = $('#subrace').val();
    const baseRace = (raceVal && RACES[raceVal]) || {};
    const subRaceCfg = (baseRace.subrace && subraceVal && baseRace.subrace[subraceVal]) || {};
    const raceErrors = [];

    const flexCfg = subRaceCfg.flexible_ability || baseRace.flexible_ability;
    if(flexCfg && Array.isArray(flexCfg.picks) && flexCfg.picks.length){
      const requiredPicks = flexCfg.picks.length;
      const picked = [];
      $('#race-options-body .race-ability-pick').each(function(){
        const val = $(this).val();
        if(val){ picked.push(val); }
      });
      if(picked.length !== requiredPicks){
        raceErrors.push('Select all racial ability bonuses.');
      }
    }

    const skillCfg = subRaceCfg.skill_choices || baseRace.skill_choices;
    if(skillCfg && skillCfg.count){
      const expected = parseInt(skillCfg.count, 10) || 0;
      if(expected > 0){
        const chosen = $('#race-options-body .cb-race-skill:checked').length;
        if(chosen !== expected){
          raceErrors.push(expected === 1 ? 'Choose 1 racial skill.' : `Choose ${expected} racial skills.`);
        }
      }
    }

    const languageCfg = subRaceCfg.language_choices || baseRace.language_choices;
    if(languageCfg && languageCfg.count){
      const expectedLang = parseInt(languageCfg.count, 10) || 0;
      if(expectedLang > 0){
        const chosenLang = $('#race-options-body .cb-race-language:checked').length;
        if(chosenLang !== expectedLang){
          raceErrors.push(expectedLang === 1 ? 'Choose 1 bonus language.' : `Choose ${expectedLang} bonus languages.`);
        }
      }
    }

    if(raceErrors.length){
      $('#builder-msg').html(`<div class="alert alert-danger">${raceErrors.join('<br>')}</div>`);
      return;
    }

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
  const raceAbility = {};
  $('#race-options-body .race-ability-pick').each(function(){
    const ability = $(this).val();
    const bonus = parseInt($(this).data('amount'), 10) || 0;
    if(ability && bonus){
      raceAbility[ability] = (raceAbility[ability] || 0) + bonus;
    }
  });
  if(Object.keys(raceAbility).length){ fd.append('race_ability_bonuses', JSON.stringify(raceAbility)); }
  const raceSkills = [];
  $('#race-options-body .cb-race-skill:checked').each(function(){ raceSkills.push($(this).data('name')); });
  if(raceSkills.length) fd.append('race_skills', JSON.stringify(raceSkills));
  const raceLanguages = [];
  $('#race-options-body .cb-race-language:checked').each(function(){ raceLanguages.push($(this).data('name')); });
  if(raceLanguages.length) fd.append('race_languages', JSON.stringify(raceLanguages));
  const feats = [];
  $('#class-options-body .cb-feat:checked').each(function(){ feats.push($(this).data('name')); });
  if(feats.length) fd.append('feats', JSON.stringify(feats));

  const submitUrl = (formEl.dataset && formEl.dataset.submitUrl) ? formEl.dataset.submitUrl : '/create_character';
    $.ajax({
      type: 'POST', url: submitUrl, data: fd, dataType: 'json',
      processData: false,
      contentType: false,
      success: function(resp){
        if(resp.error){
          $('#builder-msg').html(`<div class="alert alert-danger">${resp.error}</div>`);
        } else {
          const msg = editMode ? 'Character updated!' : 'Character created!';
          $('#builder-msg').html(`<div class="alert alert-success">${msg}</div>`);
          // If coming from player flow, go to character_selection. Else back home.
          const next = resp.redirect || '/';
          setTimeout(()=> window.location.href = next, 800);
        }
      },
      error: function(){
        const msg = editMode ? 'Failed to update character.' : 'Failed to create character.';
        $('#builder-msg').html(`<div class="alert alert-danger">${msg}</div>`);
      }
    });
  });

  function prefillEditCharacter(){
    if(!editMode || !EDIT_CHARACTER) return;
    const ec = EDIT_CHARACTER;
    $('#name').val(ec.name || '');
    $('#pronoun').val(ec.pronoun || '');
    $('#race').val(ec.race || '');
    $('#race').trigger('change');
    if(ec.subrace){
      $('#subrace').val(ec.subrace);
    }
    $('#klass').val(ec.klass || '');
    $('#level').val(String(ec.level || 1));

    const ability = ec.ability || {};
    abilities.forEach(ab=>{
      const score = parseInt(ability[ab] || $(`#input-${ab}`).val() || 8, 10);
      setVal(ab, score);
    });
    $('#points-remaining').text('-');

    renderRaceOptions();
    renderClassOptions();

    const markChecked = (selector, values)=>{
      const wanted = new Set(values || []);
      $(selector).each(function(){
        const name = $(this).data('name');
        if(wanted.has(name)){
          $(this).prop('checked', true).trigger('change');
        }
      });
    };
    markChecked('#class-options-body .cb-skill', ec.skills || []);
    markChecked('#class-options-body .cb-cantrip', ec.cantrips || []);
    markChecked('#class-options-body .cb-lvl1', ec.level1_spells || []);
    markChecked('#class-options-body .cb-feat', ec.feats || []);
  }

  // init
  updatePoints();
  renderRaceOptions();
  prefillEditCharacter();
})();
