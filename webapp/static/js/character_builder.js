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

  function getBackgrounds(){
    const el = document.getElementById('backgrounds-data');
    if(!el) return {};
    try { return JSON.parse(el.textContent || '{}'); } catch(e){ return {}; }
  }
  const BACKGROUNDS = getBackgrounds();
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
  $('#background').on('change', renderBackgroundOptions);
  // initial hide
  $('#class-options').hide();
  $('#race-options').hide();
  $('#background-options').hide();

  // ---------- Background Options ----------
  function renderBackgroundOptions(){
    const bg = $('#background').val();
    const $panel = $('#background-options');
    const $body = $('#background-options-body');
    $body.empty();
    $body.off();
    if(!bg || !BACKGROUNDS[bg]){
      $panel.hide();
      return;
    }
    const bdata = BACKGROUNDS[bg];
    $panel.show();

    // Description
    if(bdata.description){
      $body.append(`<p class="helper" style="margin-bottom:10px;">${bdata.description.substring(0, 200)}${bdata.description.length > 200 ? '...' : ''}</p>`);
    }

    // Skill proficiencies (always granted)
    if(bdata.skill_proficiencies && bdata.skill_proficiencies.length){
      const skillsLabel = bdata.skill_proficiencies.map(s => s.replace(/_/g,' ')).join(', ');
      $body.append(`<div class="form-group"><label>Skill Proficiencies</label><div class="helper">${skillsLabel}</div></div>`);
    }

    // Tool proficiencies (always granted)
    if(bdata.tool_proficiencies && bdata.tool_proficiencies.length){
      const toolsLabel = bdata.tool_proficiencies.map(t => t.replace(/_/g,' ')).join(', ');
      $body.append(`<div class="form-group"><label>Tool Proficiencies</label><div class="helper">${toolsLabel}</div></div>`);
    }

    // Feature
    if(bdata.feature && bdata.feature.name){
      $body.append(`<div class="form-group"><label>Feature: ${bdata.feature.name}</label><div class="helper">${bdata.feature.description.substring(0, 150)}${bdata.feature.description.length > 150 ? '...' : ''}</div></div>`);
    }

    // Language choices
    const choiceCount = parseInt(bdata.language_choice_count || 0, 10);
    const pool = bdata.languages_pool || [];
    if(choiceCount > 0 && pool.length){
      const langWrap = $('<div class="form-group"/>');
      langWrap.append(`<label>Background Languages: choose ${choiceCount}</label>`);
      const row = $('<div class="row"/>');
      // Deduplicate pool
      const uniquePool = [...new Set(pool)];
      uniquePool.forEach((lang, idx)=>{
        const col = $('<div class="col-xs-6 col-sm-4 col-md-3"/>');
        const id = `bg-language-${idx}`;
        col.append(`
          <div class="checkbox">
            <label>
              <input type="checkbox" class="cb-bg-language" data-name="${lang}" id="${id}"> ${lang.replace(/_/g,' ')}
            </label>
          </div>`);
        row.append(col);
      });
      langWrap.append(row);
      langWrap.append(`<div class="helper" id="bg-language-helper">${choiceCount} remaining</div>`);
      $body.append(langWrap);

      $body.on('change', '.cb-bg-language', function(){
        const selected = $body.find('.cb-bg-language:checked').length;
        const remaining = Math.max(0, choiceCount - selected);
        $('#bg-language-helper').text(`${remaining} remaining`);
        if(selected >= choiceCount){
          $body.find('.cb-bg-language:not(:checked)').prop('disabled', true);
        } else {
          $body.find('.cb-bg-language').prop('disabled', false);
        }
      });
    }
  }

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

  // Background language choices
  const bgLanguages = [];
  $('#background-options-body .cb-bg-language:checked').each(function(){ bgLanguages.push($(this).data('name')); });
  if(bgLanguages.length) fd.append('background_languages', JSON.stringify(bgLanguages));

  // Append inventory
  if(typeof window.getInventoryForSubmit === 'function'){
    const inv = window.getInventoryForSubmit();
    if(inv && inv.length){
      fd.append('inventory', JSON.stringify(inv));
    }
  }

  // Validate background selection
  const bgVal = $('#background').val();
  const bgDef = bgVal ? BACKGROUNDS[bgVal] : null;
  if(bgDef){
    const expectedBgLang = parseInt(bgDef.language_choice_count || 0, 10);
    if(expectedBgLang > 0 && bgLanguages.length !== expectedBgLang){
      $('#builder-msg').html(`<div class="alert alert-danger">Choose ${expectedBgLang} background language${expectedBgLang > 1 ? 's' : ''}.</div>`);
      return;
    }
  }

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

  // Equipment Pack Preview Functionality
  function setupEquipmentPackPreview() {
    const packSelect = document.getElementById('equipment_pack');
    const previewPanel = document.getElementById('equipment_pack_preview');
    const previewName = document.getElementById('preview_pack_name');
    const previewCost = document.getElementById('preview_pack_cost');
    const previewItems = document.getElementById('preview_items');
    
    if (!packSelect || !previewPanel) return;
    
    // Get equipment packs data from the page
    const packsDataEl = document.getElementById('equipment-packs-data');
    if (!packsDataEl) return;
    
    let equipmentPacks = {};
    try {
      equipmentPacks = JSON.parse(packsDataEl.textContent || '{}');
    } catch(e) {
      console.error('Failed to parse equipment packs data:', e);
      return;
    }
    
    packSelect.addEventListener('change', function() {
      const selectedPackId = this.value;
      
      if (!selectedPackId || !equipmentPacks[selectedPackId]) {
        previewPanel.style.display = 'none';
        return;
      }
      
      const pack = equipmentPacks[selectedPackId];
      
      // Update preview header
      previewName.textContent = pack.name;
      previewCost.textContent = `${pack.cost} gp`;
      
      // Build items list
      previewItems.innerHTML = '';
      
      if (pack.items && Array.isArray(pack.items)) {
        pack.items.forEach(item => {
          const li = document.createElement('li');
          li.className = 'preview-item';
          
          // Handle both object format {item_name: qty} and string format
          if (typeof item === 'object') {
            const itemName = Object.keys(item)[0];
            const qty = item[itemName];
            li.innerHTML = `<span class="item-name">${itemName.replace(/_/g, ' ')}</span> <span class="item-qty">×${qty}</span>`;
          } else {
            li.textContent = item.replace(/_/g, ' ');
          }
          
          previewItems.appendChild(li);
        });
      }
      
      // Show preview panel
      previewPanel.style.display = 'block';
    });
  }
  
  function setupDndBeyondImport(){
    if(editMode) return;
    const $btn = $('#ddb-import-btn');
    const $url = $('#ddb-url');
    const $cobalt = $('#ddb-cobalt');
    const $status = $('#ddb-import-status');
    if(!$btn.length || !$url.length) return;

    $btn.on('click', function(){
      const sheetUrl = ($url.val() || '').trim();
      if(!sheetUrl){
        $('#builder-msg').html('<div class="alert alert-danger">Enter a D&amp;D Beyond character sheet URL.</div>');
        return;
      }
      $btn.prop('disabled', true);
      $status.text('Importing…');
      $('#builder-msg').html('<div class="alert alert-info">Fetching character from D&amp;D Beyond…</div>');

      $.ajax({
        type: 'POST',
        url: '/character_builder/import_dndbeyond',
        contentType: 'application/json',
        data: JSON.stringify({
          url: sheetUrl,
          cobalt_token: ($cobalt.val() || '').trim() || undefined,
        }),
        dataType: 'json',
        success: function(resp){
          if(resp.error){
            $('#builder-msg').html(`<div class="alert alert-danger">${resp.error}</div>`);
            $status.text('');
            $btn.prop('disabled', false);
            return;
          }
          let html = `<div class="alert alert-success">Imported <strong>${resp.character_name || 'character'}</strong>.</div>`;
          if(resp.warnings && resp.warnings.length){
            const list = resp.warnings.map(w => `<li>${$('<div>').text(w).html()}</li>`).join('');
            html += `<div class="alert alert-warning" style="margin-top:8px;"><strong>Some data was skipped:</strong><ul style="margin:8px 0 0 18px;">${list}</ul></div>`;
          }
          $('#builder-msg').html(html);
          $status.text('Done');
          const next = resp.redirect || '/';
          setTimeout(()=> { window.location.href = next; }, resp.warnings && resp.warnings.length ? 1800 : 900);
        },
        error: function(xhr){
          let msg = 'Failed to import from D&amp;D Beyond.';
          try {
            const body = xhr.responseJSON || JSON.parse(xhr.responseText || '{}');
            if(body.error) msg = body.error;
          } catch(e) { /* ignore */ }
          $('#builder-msg').html(`<div class="alert alert-danger">${msg}</div>`);
          $status.text('');
          $btn.prop('disabled', false);
        }
      });
    });
  }

  // ---- Inventory Manager ----
  function setupInventoryManager(){
    // State
    let availableItems = {};  // id -> {id, name, type, cost, weight, category}
    let inventory = [];       // [{item: id, qty: n}]

    // DOM refs
    const $search = $('#inventory-item-search');
    const $select = $('#inventory-item-select');
    const $qty = $('#inventory-item-qty');
    const $addBtn = $('#add-inventory-item-btn');
    const $info = $('#inventory-item-info');
    const $emptyMsg = $('#inventory-empty-msg');
    const $table = $('#inventory-table');
    const $tbody = $('#inventory-tbody');
    const $summary = $('#inventory-summary');
    const $totalWeight = $('#inventory-total-weight');

    // Load items from server
    $.ajax({
      url: '/character_builder/items',
      method: 'GET',
      dataType: 'json',
      timeout: 10000,
    }).done(function(resp){
      availableItems = resp.items || {};
      populateItemSelect();
      // Load existing inventory for edit mode
      if(editMode && EDIT_CHARACTER && EDIT_CHARACTER.inventory){
        inventory = EDIT_CHARACTER.inventory.map(function(entry){
          return { item: entry.item || entry.type, qty: entry.qty || 1 };
        });
        renderInventory();
      }
    }).fail(function(jqXHR, textStatus, errorThrown){
      console.error('Failed to load inventory items:', textStatus, errorThrown, jqXHR.status, jqXHR.responseText);
      $select.html('<option value="">-- Failed to load items (' + textStatus + ') --</option>');
    });

    function populateItemSelect(filter){
      $select.empty();
      const items = Object.values(availableItems).sort(function(a, b){
        return a.name.localeCompare(b.name);
      });
      const filtered = filter
        ? items.filter(function(it){ return it.name.toLowerCase().indexOf(filter) >= 0; })
        : items;
      $select.append('<option value="">-- Select an item --</option>');
      filtered.forEach(function(it){
        const cat = it.category || it.type || '';
        $select.append(`<option value="${it.id}">${it.name} (${cat})</option>`);
      });
    }

    // Search filter
    $search.on('input', function(){
      populateItemSelect($(this).val().toLowerCase().trim());
    });

    // Show item info on select
    $select.on('change', function(){
      const id = $(this).val();
      if(!id || !availableItems[id]){
        $info.html('Select an item to see details.');
        return;
      }
      const it = availableItems[id];
      $info.html(`
        <strong>${it.name}</strong><br>
        Type: ${it.type || '—'}<br>
        Cost: ${it.cost || '—'} gp<br>
        Weight: ${it.weight || 0} lbs
      `);
    });

    // Add item
    $addBtn.on('click', function(){
      const id = $select.val();
      if(!id){
        alert('Please select an item.');
        return;
      }
      const q = parseInt($qty.val() || '1', 10);
      if(q < 1){
        alert('Quantity must be at least 1.');
        return;
      }
      // Check if already in inventory
      const existing = inventory.find(function(e){ return e.item === id; });
      if(existing){
        existing.qty += q;
      } else {
        inventory.push({ item: id, qty: q });
      }
      renderInventory();
      $select.val('');
      $qty.val('1');
      $info.html('Item added!');
      setTimeout(function(){ $info.html('Select an item to see details.'); }, 1200);
    });

    // Render inventory table
    function renderInventory(){
      $tbody.empty();
      if(inventory.length === 0){
        $emptyMsg.show();
        $table.hide();
        $summary.hide();
        return;
      }
      $emptyMsg.hide();
      $table.show();
      let totalWeight = 0;
      inventory.forEach(function(entry, idx){
        const it = availableItems[entry.item] || { name: entry.item, type: '', cost: '', weight: 0 };
        const w = parseFloat(it.weight || 0);
        totalWeight += w * entry.qty;
        const tr = $(`
          <tr data-idx="${idx}">
            <td>${it.name}</td>
            <td>${it.type || '—'}</td>
            <td><input type="number" class="form-control inv-qty" value="${entry.qty}" min="0" max="999" style="width:80px;display:inline-block;"></td>
            <td>${it.cost || '—'}</td>
            <td>${(w * entry.qty).toFixed(1)}</td>
            <td>
              <button type="button" class="btn btn-danger btn-xs inv-remove">Remove</button>
            </td>
          </tr>
        `);
        $tbody.append(tr);
      });
      $summary.show();
      $totalWeight.text(`Total weight: ${totalWeight.toFixed(1)} lbs`);

      // Qty change
      $tbody.on('input', '.inv-qty', function(){
        const idx = parseInt($(this).closest('tr').data('idx'), 10);
        const q = parseInt($(this).val() || '0', 10);
        if(q <= 0){
          inventory.splice(idx, 1);
        } else {
          inventory[idx].qty = q;
        }
        renderInventory();
      });

      // Remove
      $tbody.on('click', '.inv-remove', function(){
        const idx = parseInt($(this).closest('tr').data('idx'), 10);
        inventory.splice(idx, 1);
        renderInventory();
      });
    }

    // Expose inventory for form submission
    window.getInventoryForSubmit = function(){
      return inventory;
    };
  }

  // init
  updatePoints();
  renderRaceOptions();
  renderBackgroundOptions();
  prefillEditCharacter();
  setupEquipmentPackPreview();
  setupDndBeyondImport();
  setupInventoryManager();
})();
