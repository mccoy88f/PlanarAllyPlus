/* global window — scheda D&D 5e stile scheda_dnd5e_IT, usata da index.html */
(function () {
  'use strict';

  var SKILLS_BY_ABILITY = {
    str: ['athletics'],
    dex: ['acrobatics', 'stealth', 'sleightOfHand'],
    con: [],
    int: ['arcana', 'investigation', 'nature', 'religion', 'history'],
    wis: ['animalHandling', 'insight', 'medicine', 'perception', 'survival'],
    cha: ['deception', 'intimidation', 'performance', 'persuasion']
  };

  function escHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }

  function formatMarkdownBold(s) {
    if (!s) return '';
    return escHtml(s).replace(/\*\*([\s\S]*?)\*\*/g, '<strong>$1</strong>');
  }

  function injectQeLinksHtml(text, names, esc) {
    if (!text) return text;
    var safe = esc(text);
    var placeholders = [];
    var ph = function () {
      var id = '\x01QE' + placeholders.length + '\x02';
      placeholders.push(null);
      return id;
    };
    safe = safe.replace(/\[([^\]]*)\]\(qe:([^)]+)\)/gi, function (_, linkText, path) {
      var parts = path.split('/');
      var comp = parts.length >= 3 ? parts[0] : '';
      var coll = parts.length >= 3 ? parts[1] : parts[0];
      var slug = parts.length >= 3 ? parts[2] : parts[1];
      var attrs = 'data-qe-collection="' + esc(coll) + '" data-qe-slug="' + esc(slug) + '"';
      if (comp) attrs = 'data-qe-compendium="' + esc(comp) + '" ' + attrs;
      var link = '<a href="#" ' + attrs + ' class="qe-internal-link">' + esc(linkText) + '</a>';
      var id = ph();
      placeholders[placeholders.length - 1] = link;
      return id;
    });
    if (names.length) {
      names = names.slice().sort(function (a, b) {
        return (b.name || '').length - (a.name || '').length;
      });
      for (var i = 0; i < names.length; i++) {
        var e = names[i];
        if (!e || !e.name) continue;
        var escName = e.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        var attrs = 'data-qe-collection="' + esc(e.collectionSlug || '') + '" data-qe-slug="' + esc(e.itemSlug || '') + '"';
        if (e.compendiumSlug) attrs = 'data-qe-compendium="' + esc(e.compendiumSlug) + '" ' + attrs;
        var link = '<a href="#" ' + attrs + ' class="qe-internal-link">' + esc(e.name) + '</a>';
        safe = safe.replace(new RegExp('"(' + escName + ')"', 'gi'), function () {
          var id = ph();
          placeholders[placeholders.length - 1] = '"' + link + '"';
          return id;
        });
        safe = safe.replace(new RegExp('\\(' + escName + '\\)', 'gi'), function () {
          var id = ph();
          placeholders[placeholders.length - 1] = '(' + link + ')';
          return id;
        });
        safe = safe.replace(new RegExp('\\b(' + escName + ')\\b', 'gi'), function () {
          var id = ph();
          placeholders[placeholders.length - 1] = link;
          return id;
        });
      }
    }
    for (var j = 0; j < placeholders.length; j++) {
      safe = safe.replace('\x01QE' + j + '\x02', placeholders[j] || '');
    }
    return safe.replace(/\*\*([\s\S]*?)\*\*/g, '<strong>$1</strong>');
  }

  function deathDots(name, val, isView) {
    var v = parseInt(val, 10) || 0;
    var h = '';
    for (var i = 1; i <= 3; i++) {
      var on = v >= i ? ' filled' : '';
      h += '<span class="ts-dot' + on + '" data-death="' + name + '" data-val="' + i + '"></span>';
    }
    return '<div class="ts-dots">' + h + '</div>';
  }

  function deathDotsSuccess(name, val, isView) {
    var v = parseInt(val, 10) || 0;
    var h = '';
    for (var i = 1; i <= 3; i++) {
      var on = v >= i ? ' filled' : '';
      h += '<span class="ts-dot success' + on + '" data-death="' + name + '" data-val="' + i + '"></span>';
    }
    return '<div class="ts-dots">' + h + '</div>';
  }

  window.PA_sheetIt5eRender = function (ctx) {
    var f = ctx.formData || {};
    var isView = ctx.isView;
    var t = ctx.t;
    var currentTab = ctx.currentTab;
    var characters = ctx.characters || [];
    var sheets = ctx.sheets || [];
    var selectedId = ctx.selectedId;
    var qeEnabled = ctx.qeEnabled;
    var qeNamesCache = ctx.qeNamesCache || [];
    var SKILL_KEYS = ctx.SKILL_KEYS;
    var SKILL_ABILITY = ctx.SKILL_ABILITY;
    var skillStatHint = ctx.skillStatHint;

    var esc = escHtml;
    var cur = sheets.find(function (s) {
      return s.id === selectedId;
    });

    function inp(field, val, attrs) {
      var ro = isView ? ' readonly' : '';
      return '<input type="text" data-field="' + field + '" value="' + esc(String(val != null ? val : '')) + '"' + (attrs || '') + ro + ' />';
    }

    function inpNum(field, val, attrs) {
      var ro = isView ? ' readonly' : '';
      return '<input type="number" data-field="' + field + '" value="' + esc(String(val != null ? val : '')) + '"' + (attrs || '') + ro + ' />';
    }

    function txt(field, val, rows, minH) {
      if (isView) {
        var raw = esc(val || '');
        var content = qeEnabled ? injectQeLinksHtml(val || '', qeNamesCache, esc) : formatMarkdownBold(val || '');
        var mh = minH || Math.max(60, (rows || 3) * 22);
        return (
          '<input type="hidden" data-field="' +
          field +
          '" value="' +
          raw +
          '" /><div class="cs-txt-view cs-markdown" style="min-height:' +
          mh +
          'px">' +
          content +
          '</div>'
        );
      }
      return '<textarea data-field="' + field + '" rows="' + (rows || 3) + '" style="width:100%">' + esc(val || '') + '</textarea>';
    }

    /** Campi su una riga (tabella armi, cast/gittata/note incantesimi): in sola lettura con compendio come txt() / nome incantesimo. */
    function inpQeInline(field, val, attrs, opts) {
      opts = opts || {};
      if (isView && qeEnabled) {
        var raw = esc(String(val != null ? val : ''));
        var content = injectQeLinksHtml(val || '', qeNamesCache, esc);
        var fontSize = opts.fontSize || '0.7rem';
        var style = 'font-size:' + fontSize + ';line-height:1.25';
        if (attrs && attrs.indexOf('flex:1') !== -1) style += ';flex:1;min-width:0';
        return (
          '<input type="hidden" data-field="' +
          field +
          '" value="' +
          raw +
          '" /><div class="cs-markdown cs-qe-inline-view" style="' +
          style +
          '">' +
          content +
          '</div>'
        );
      }
      return inp(field, val, attrs);
    }

    function inpSpellName(field, val) {
      return inpQeInline(field, val, '', { fontSize: '0.64rem' });
    }

    function skillLabel(key) {
      if (key === 'sleightOfHand') return t('sleightOfHandSheet');
      return t(key);
    }

    function abilityBlock(ab) {
      var skills = SKILLS_BY_ABILITY[ab] || [];
      var modVal = f[ab + 'Mod'] !== '' && f[ab + 'Mod'] != null ? String(f[ab + 'Mod']) : ctx.mod(f[ab]);
      var html = '<div class="ability-block">';
      html += '<div class="ability-name">' + t('ability_' + ab) + '</div>';
      html += '<div class="ability-scores">';
      html += '<div class="field-group ability-main">';
      html += '<div class="field-label" style="text-align:center">' + t('score') + '</div>';
      html += inpNum(ab, f[ab], ' min="1" max="30" placeholder="—"');
      html += '</div>';
      html += '<div class="field-group ability-mod">';
      html += '<div class="field-label">' + t('modifier') + '</div>';
      html += inp(ab + 'Mod', modVal, ' placeholder="—"');
      html += '</div></div>';
      var sv = f[ab + 'SaveChecked'] ? ' checked' : '';
      html += '<div class="ts-row">';
      html += '<input type="checkbox" data-save-check="' + ab + '"' + sv + (isView ? ' disabled' : '') + ' />';
      html += '<input type="text" class="skill-mod-in" data-field="' + ab + 'Save" value="' + esc(f[ab + 'Save'] || '0') + '" style="width:34px"' + (isView ? ' readonly' : '') + ' />';
      html += '<span>' + t('savingThrowShort') + '</span></div>';
      if (skills.length) {
        html += '<div class="skills-cols">';
        skills.forEach(function (sk) {
          var key = 'skill' + sk.charAt(0).toUpperCase() + sk.slice(1);
          var ck = f[key + 'Checked'] ? ' checked' : '';
          html += '<div class="skill-row">';
          html += '<input type="checkbox" data-skill-check="' + sk + '"' + ck + (isView ? ' disabled' : '') + ' />';
          html +=
            '<input type="text" class="skill-mod-in" data-field="' +
            key +
            '" value="' +
            esc(f[key] || '0') +
            '"' +
            (isView ? ' readonly' : '') +
            ' />';
          html += '<span class="skill-name">' + skillLabel(sk) + ' <span style="color:var(--text-3);font-size:0.62rem">' + (SKILL_ABILITY[sk] ? skillStatHint(sk) : '') + '</span></span></div>';
        });
        html += '</div>';
      }
      html += '</div>';
      return html;
    }

    var charOpts = '<option value="">— ' + t('none') + ' —</option>';
    characters.forEach(function (c) {
      var sel = cur && cur.characterId === c.id ? ' selected' : '';
      charOpts += '<option value="' + c.id + '"' + sel + '>' + esc(c.name) + '</option>';
    });

    var weaponRows = f.weaponRows && f.weaponRows.length ? f.weaponRows : [];
    if (!weaponRows.length) {
      weaponRows = [];
      for (var wi = 0; wi < 3; wi++) {
        var a = (f.attacks || [])[wi] || {};
        weaponRows.push({ name: a.name || '', bonus: a.bonus || '', damage: a.damage || '', notes: '' });
      }
      while (weaponRows.length < 5) weaponRows.push({ name: '', bonus: '', damage: '', notes: '' });
    }

    var spellRows = f.spellBookRows && f.spellBookRows.length ? f.spellBookRows : [];
    while (spellRows.length < 20) spellRows.push({});

    var html = '';
    html += '<div class="cs-sheet-it5e-wrap">';

    /* —— Pagina 1 —— */
    html += '<div class="tab-page' + (currentTab === 'main' ? ' active' : '') + '" data-cs-tab="main">';
    html += '<div class="sheet">';
    html += '<div class="hdr-grid">';
    html += '<div class="field-group"><div class="field-label">' + t('name') + '</div>' + inp('name', f.name, ' class="input-nome" placeholder=""') + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('assignToken') + '</div><select id="charSelect" class="cs-char-select"' + (isView ? ' disabled' : '') + '>' + charOpts + '</select></div>';
    html += '<div class="field-group"><div class="field-label">' + t('level') + '</div>' + inpNum('sheetLevel', f.sheetLevel, ' min="1" max="99" placeholder="—"') + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('xp') + '</div>' + inpNum('xp', f.xp, ' min="0" placeholder="—"') + '</div>';
    html += '</div>';

    html += '<div class="hdr-grid-2">';
    html += '<div class="field-group"><div class="field-label">' + t('background') + '</div>' + inp('background', f.background) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('classOnly') + '</div>' + inp('classNameOnly', f.classNameOnly) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('subclass') + '</div>' + inp('subclass', f.subclass) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('species') + '</div>' + inp('race', f.race) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('alignment') + '</div>' + inp('alignment', f.alignment) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('playerName') + '</div>' + inp('playerName', f.playerName) + '</div>';
    html += '</div>';

    html += '<hr class="divider">';

    html += '<div class="topstats">';
    html += '<div class="box topstat-cell topstat-center"><div class="box-label">' + t('proficiencyBonus') + '</div><div class="topstat-circle">' + inp('proficiencyBonus', f.proficiencyBonus) + '</div></div>';
    html += '<div class="box topstat-cell topstat-center"><div class="box-label">' + t('initiative') + '</div><div class="topstat-circle">' + inp('init', f.init) + '</div></div>';
    html += '<div class="box topstat-cell topstat-center"><div class="box-label">' + t('armourClass') + '</div><div class="topstat-circle">' + inp('ac', f.ac) + '</div>';
    var sh = f.shieldEquipped ? ' checked' : '';
    html += '<label class="topstat-check"><input type="checkbox" data-field="shieldEquipped"' + sh + (isView ? ' disabled' : '') + ' /> ' + t('shield') + '</label></div>';
    html += '<div class="box topstat-cell"><div class="box-label">' + t('hitPoints') + '</div><div class="pf-grid">';
    html += '<div class="field-group"><div class="field-label">' + t('hpCurrent') + '</div>' + inpNum('hp', f.hp) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('tempHp') + '</div>' + inpNum('tempHp', f.tempHp) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('maxHp') + '</div>' + inpNum('maxHp', f.maxHp) + '</div>';
    html += '</div><hr style="border:none;border-top:1px solid var(--border);margin:6px 0;"><div class="box-label">' + t('hitDice') + '</div><div class="dadi-grid">';
    html += '<div class="field-group"><div class="field-label">' + t('hitDiceType') + '</div>' + inp('hitDiceType', f.hitDiceType) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('hitDiceSpent') + '</div>' + inpNum('hitDiceSpent', f.hitDiceSpent) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('hitDiceMax') + '</div>' + inp('hitDiceMax', f.hitDiceMax) + '</div>';
    html += '</div></div>';
    html += '<div class="box topstat-cell topstat-center ts-morte-box"><div class="box-label">' + t('deathSaves') + '</div><div class="ts-morte-compact">';
    html += '<div class="ts-morte-row"><span class="ts-morte-label">✓</span>' + deathDotsSuccess('deathsaveSuccesses', f.deathsaveSuccesses, isView) + '</div>';
    html += '<div class="ts-morte-row"><span class="ts-morte-label">✗</span>' + deathDots('deathsaveFailures', f.deathsaveFailures, isView) + '</div>';
    html += '</div></div></div>';

    html += '<hr class="divider"><div class="main-layout"><div class="left-col">';
    ['str', 'dex', 'con', 'int', 'wis', 'cha'].forEach(function (ab) {
      html += abilityBlock(ab);
    });
    html += '</div><div class="right-col">';

    html += '<div class="mid-stats">';
    var inspActive = f.inspiration === '1' ? ' active' : '';
    html += '<div class="box mid-stat"><div class="box-label">' + t('inspiration') + '</div><span class="star-toggle' + inspActive + '" data-inspiration-toggle="1" role="button" tabindex="0">✦</span></div>';
    html += '<div class="box mid-stat"><div class="box-label">' + t('passivePerception') + '</div>' + inpNum('passivePerception', f.passivePerception) + '</div>';
    html += '<div class="box mid-stat"><div class="field-label">' + t('speed') + '</div>' + inp('speed', f.speed) + '</div>';
    html += '<div class="box mid-stat"><div class="field-label">' + t('size') + '</div>' + inp('size', f.size) + '</div>';
    html += '</div>';

    html += '<div class="box"><div class="section-title">' + t('weaponsTitle') + '</div><table class="weapons-table"><thead><tr>';
    html += '<th style="width:28%">' + t('attackName') + '</th><th style="width:16%">' + t('atkBonus') + ' / CD</th><th style="width:22%">' + t('damageType') + '</th><th>' + t('notes') + '</th></tr></thead><tbody id="weapons-body">';
    weaponRows.forEach(function (w, idx) {
      html += '<tr data-weapon-row="' + idx + '"><td>' + inpQeInline('weapon_' + idx + '_name', w.name) + '</td><td>' + inpQeInline('weapon_' + idx + '_bonus', w.bonus) + '</td><td>' + inpQeInline('weapon_' + idx + '_damage', w.damage) + '</td><td style="display:flex;gap:4px;align-items:center">';
      html += inpQeInline('weapon_' + idx + '_notes', w.notes, ' style="flex:1"');
      if (!isView) html += '<button type="button" class="weapon-row-remove" data-weapon-remove="' + idx + '" title="">✕</button>';
      html += '</td></tr>';
    });
    html += '</tbody></table>';
    if (!isView) html += '<button type="button" class="add-btn" data-add-weapon="1">+ ' + t('addWeapon') + '</button>';
    html += '</div>';

    html += '<div class="box"><div class="section-title">' + t('classFeatures') + '</div>' + txt('classFeatures', f.classFeatures, 6, 120) + '</div>';
    html += '<div class="bottom-right"><div class="box"><div class="section-title">' + t('speciesTraits') + '</div>' + txt('speciesTraits', f.speciesTraits, 4, 100) + '</div>';
    html += '<div class="box"><div class="section-title">' + t('feats') + '</div>' + txt('feats', f.feats, 4, 100) + '</div></div>';

    html += '<div class="bottom-bar"><div class="box"><div class="section-title">' + t('equipmentTraining') + '</div>';
    html += '<div class="field-label" style="margin-bottom:4px">' + t('armorProf') + '</div><div class="armor-checks">';
    [['armorLight', t('armorLight')], ['armorMedium', t('armorMedium')], ['armorHeavy', t('armorHeavy')], ['armorShields', t('armorShields')]].forEach(function (pair) {
      var c = f[pair[0]] ? ' checked' : '';
      html += '<label class="armor-check"><input type="checkbox" data-field="' + pair[0] + '"' + c + (isView ? ' disabled' : '') + ' /><span> ' + pair[1] + '</span></label>';
    });
    html += '</div><hr class="divider"><div class="field-label">' + t('weaponsProf') + '</div>' + txt('weaponsProfText', f.weaponsProfText, 2, 44);
    html += '<div class="field-label" style="margin-top:4px">' + t('toolsProf') + '</div>' + txt('toolsProfText', f.toolsProfText, 2, 40);
    html += '<div class="field-label" style="margin-top:6px">' + t('otherProficiencies') + '</div>' + txt('otherProficiencies', f.otherProficiencies, 4, 80);
    html += '</div>';

    html += '<div class="box" style="display:flex;flex-direction:column;gap:6px"><div class="section-title">' + t('equipment') + '</div>';
    html += txt('equipment', f.equipment, 6, 120);
    html += '<div class="field-label" style="margin-top:4px">' + t('equipment2') + '</div>' + txt('equipment2', f.equipment2, 2, 48);
    html += '<hr class="divider"><div class="section-title">' + t('currency') + '</div><div class="denari-grid">';
    ['cp', 'sp', 'ep', 'gp', 'pp'].forEach(function (c) {
      html += '<div class="denaro-item"><div class="denaro-label">' + t(c) + '</div>' + inpNum(c, f[c]) + '</div>';
    });
    html += '</div></div></div></div></div></div></div>';

    /* —— Pagina 2 —— */
    html += '<div class="tab-page' + (currentTab === 'spells' ? ' active' : '') + '" data-cs-tab="spells">';
    html += '<div class="sheet">';
    html += '<div class="p2-layout"><div class="p2-left">';

    html += '<div class="box"><div class="section-title">' + t('spellcastingStats') + '</div><div class="spell-stats">';
    html += '<div class="field-group"><div class="field-label">' + t('spellAbility') + '</div>' + inp('spellcastingAbility', f.spellcastingAbility) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('spellMod') + '</div>' + inp('spellcastingModText', f.spellcastingModText) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('spellSaveDC') + '</div>' + inp('spellSaveDC', f.spellSaveDC) + '</div>';
    html += '<div class="field-group"><div class="field-label">' + t('spellAttackBonus') + '</div>' + inp('spellAttackBonus', f.spellAttackBonus) + '</div>';
    html += '</div></div>';

    html += '<div class="box"><div class="section-title">' + t('spellSlots') + '</div><div class="slots-grid">';
    for (var sl = 1; sl <= 9; sl++) {
      var stn = 'lvl' + sl + 'SpellSlotsTotal';
      var sun = 'lvl' + sl + 'SpellSlotsUsed';
      html += '<div class="slot-level"><div class="slot-level-label">' + t('spellLevelN') + ' ' + sl + '</div><div class="slot-inputs">';
      html += '<div class="field-group"><div class="field-label">' + t('slotsTotal') + '</div>' + inpNum(stn, f[stn]) + '</div>';
      html += '<div class="field-group"><div class="field-label">' + t('slotsSpent') + '</div>' + inpNum(sun, f[sun]) + '</div>';
      html += '</div></div>';
    }
    html += '</div></div>';

    html += '<div class="box"><div class="section-title">' + t('spellListTitle') + '</div><table class="spell-list"><thead><tr>';
    html += '<th class="lvl-col">Lv</th><th class="name-col">' + t('spellName') + '</th><th class="time-col">' + t('castTime') + '</th><th class="range-col">' + t('spellRange') + '</th>';
    html += '<th class="flags-col">C/R/M</th><th>' + t('notes') + '</th></tr></thead><tbody>';
    spellRows.forEach(function (sp, si) {
      html += '<tr data-spell-row="' + si + '"><td>' + inp('spellrow_' + si + '_lvl', sp.level) + '</td><td>' + inpSpellName('spellrow_' + si + '_name', sp.name) + '</td>';
      html += '<td>' + inpQeInline('spellrow_' + si + '_cast', sp.cast, '', { fontSize: '0.64rem' }) + '</td><td>' + inpQeInline('spellrow_' + si + '_range', sp.range, '', { fontSize: '0.64rem' }) + '</td><td>';
      html += '<div style="display:flex;gap:3px;justify-content:center;align-items:center">';
      var cc = sp.conc ? ' checked' : '';
      var rc = sp.ritual ? ' checked' : '';
      var mc = sp.mat ? ' checked' : '';
      html += '<label class="spell-check"><input type="checkbox" data-spell-flags="' + si + '" data-flag="conc"' + cc + (isView ? ' disabled' : '') + ' /><span>C</span></label>';
      html += '<label class="spell-check"><input type="checkbox" data-spell-flags="' + si + '" data-flag="ritual"' + rc + (isView ? ' disabled' : '') + ' /><span>R</span></label>';
      html += '<label class="spell-check"><input type="checkbox" data-spell-flags="' + si + '" data-flag="mat"' + mc + (isView ? ' disabled' : '') + ' /><span>M</span></label>';
      html += '</div></td><td style="display:flex;gap:4px;align-items:center">';
      html += inpQeInline('spellrow_' + si + '_notes', sp.notes, ' style="flex:1;font-size:0.64rem"', { fontSize: '0.64rem' });
      if (!isView) html += '<button type="button" class="spell-row-remove" data-spell-remove="' + si + '">✕</button>';
      html += '</td></tr>';
    });
    html += '</tbody></table>';
    if (!isView) html += '<button type="button" class="add-btn" data-add-spell="1">+ ' + t('addSpell') + '</button>';
    html += '</div></div>';

    html += '<div class="p2-right">';
    var portraitUrl = f.appearance || '';
    var hasImg = portraitUrl && String(portraitUrl).trim();
    html += '<div class="box"><div class="section-title">' + t('portrait') + '</div>';
    html += '<div class="portrait-upload" data-img="appearance" style="' + (hasImg ? 'background-image:url(' + esc(portraitUrl) + ');background-size:cover;background-position:center' : '') + '">';
    if (!hasImg) {
      html += '<div class="cs-portrait-inner"><div class="portrait-icon">⬡</div><div class="portrait-hint">' + t('portraitHint') + '</div></div>';
    }
    html += '</div>';
    if (!isView) html += '<input type="file" accept="image/*" data-img-upload="appearance" style="display:none" />';
    html += '</div>';

    html += '<div class="box"><div class="section-title">' + t('appearanceText') + '</div>' + txt('appearanceText', f.appearanceText, 4, 90) + '</div>';
    html += '<div class="box"><div class="section-title">' + t('backstoryBlock') + '</div>' + txt('backstory', f.backstory, 10, 220) + '</div>';
    html += '<div class="box"><div class="section-title">' + t('languages') + '</div>' + txt('languagesText', f.languagesText, 3, 50) + '</div>';
    html += '<div class="box"><div class="section-title">' + t('attunement') + '</div><div class="sintonia">';
    html += '<div class="sintonia-item"><span class="sintonia-gem">✦</span>' + inp('attunement1', f.attunement1) + '</div>';
    html += '<div class="sintonia-item"><span class="sintonia-gem">✦</span>' + inp('attunement2', f.attunement2) + '</div>';
    html += '<div class="sintonia-item"><span class="sintonia-gem">✦</span>' + inp('attunement3', f.attunement3) + '</div>';
    html += '</div></div>';

    html += '</div></div></div></div>';

    html += '</div>';
    return html;
  };

  window.PA_sheetIt5eBindHandlers = function (editForm, f, ctx) {
    var editingEnabled = ctx.editingEnabled;
    var renderAll = ctx.renderAll;
    var toast = ctx.toast;
    var t = ctx.t;
    var api = ctx.api;

    function readWeaponRowsFromDom() {
      var trs = [].slice.call(editForm.querySelectorAll('tr[data-weapon-row]'));
      trs.sort(function (a, b) {
        return parseInt(a.getAttribute('data-weapon-row'), 10) - parseInt(b.getAttribute('data-weapon-row'), 10);
      });
      return trs.map(function (tr) {
        var idx = parseInt(tr.getAttribute('data-weapon-row'), 10);
        function gv(suffix) {
          var el = editForm.querySelector('[data-field="weapon_' + idx + '_' + suffix + '"]');
          return el ? el.value : '';
        }
        return { name: gv('name'), bonus: gv('bonus'), damage: gv('damage'), notes: gv('notes') };
      });
    }

    function readSpellRowsFromDom() {
      var trs = [].slice.call(editForm.querySelectorAll('tr[data-spell-row]'));
      trs.sort(function (a, b) {
        return parseInt(a.getAttribute('data-spell-row'), 10) - parseInt(b.getAttribute('data-spell-row'), 10);
      });
      return trs.map(function (tr) {
        var si = parseInt(tr.getAttribute('data-spell-row'), 10);
        function gv(suf) {
          var el = editForm.querySelector('[data-field="spellrow_' + si + '_' + suf + '"]');
          return el ? el.value : '';
        }
        var o = {
          level: gv('lvl'),
          name: gv('name'),
          cast: gv('cast'),
          range: gv('range'),
          notes: gv('notes'),
          prepared: false,
          conc: false,
          ritual: false,
          mat: false
        };
        editForm.querySelectorAll('[data-spell-flags="' + si + '"]').forEach(function (cb) {
          var fl = cb.getAttribute('data-flag');
          if (fl === 'conc') o.conc = cb.checked;
          if (fl === 'ritual') o.ritual = cb.checked;
          if (fl === 'mat') o.mat = cb.checked;
        });
        return o;
      });
    }

    editForm.querySelectorAll('a.qe-internal-link').forEach(function (a) {
      a.onclick = function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var comp = a.getAttribute('data-qe-compendium');
        var coll = a.getAttribute('data-qe-collection');
        var slug = a.getAttribute('data-qe-slug');
        if (coll && slug) {
          var target = window.top || window.parent;
          var msg = { type: 'planarally-open-qe', collection: coll, slug: slug };
          if (comp) msg.compendium = comp;
          target.postMessage(msg, '*');
        }
        return false;
      };
      a.addEventListener('mouseenter', function () {
        var comp = a.getAttribute('data-qe-compendium');
        var coll = a.getAttribute('data-qe-collection');
        var slug = a.getAttribute('data-qe-slug');
        if (coll && slug) {
          var target = window.top || window.parent;
          var rect = a.getBoundingClientRect();
          target.postMessage(
            {
              type: 'planarally-qe-hover',
              collection: coll,
              slug: slug,
              compendium: comp || undefined,
              clientX: rect.left,
              clientY: rect.bottom
            },
            '*'
          );
        }
      });
      a.addEventListener('mouseleave', function () {
        (window.top || window.parent).postMessage({ type: 'planarally-qe-hover-end' }, '*');
      });
    });

    if (!editingEnabled) return;

    var star = editForm.querySelector('[data-inspiration-toggle]');
    if (star) {
      star.onclick = function () {
        f.inspiration = f.inspiration === '1' ? '0' : '1';
        renderAll(f);
      };
    }

    editForm.querySelectorAll('[data-death]').forEach(function (el) {
      el.onclick = function () {
        var name = el.dataset.death;
        var target = parseInt(el.dataset.val, 10);
        var v = parseInt(f[name], 10) || 0;
        f[name] = v >= target ? target - 1 : target;
        renderAll(f);
      };
    });

    editForm.querySelectorAll('[data-save-check]').forEach(function (el) {
      el.onchange = function () {
        var a = el.dataset.saveCheck;
        f[a + 'SaveChecked'] = el.checked;
      };
    });

    editForm.querySelectorAll('[data-skill-check]').forEach(function (el) {
      el.onchange = function () {
        var k = el.dataset.skillCheck;
        var key = 'skill' + k.charAt(0).toUpperCase() + k.slice(1);
        f[key + 'Checked'] = el.checked;
      };
    });

    editForm.querySelectorAll('[data-add-weapon]').forEach(function (btn) {
      btn.onclick = function () {
        f.weaponRows = readWeaponRowsFromDom();
        f.weaponRows.push({ name: '', bonus: '', damage: '', notes: '' });
        renderAll(f);
      };
    });

    editForm.querySelectorAll('[data-weapon-remove]').forEach(function (btn) {
      btn.onclick = function () {
        var idx = parseInt(btn.getAttribute('data-weapon-remove'), 10);
        f.weaponRows = readWeaponRowsFromDom();
        f.weaponRows.splice(idx, 1);
        if (f.weaponRows.length < 1) f.weaponRows.push({ name: '', bonus: '', damage: '', notes: '' });
        renderAll(f);
      };
    });

    editForm.querySelectorAll('[data-add-spell]').forEach(function (btn) {
      btn.onclick = function () {
        f.spellBookRows = readSpellRowsFromDom();
        f.spellBookRows.push({});
        renderAll(f);
      };
    });

    editForm.querySelectorAll('[data-spell-remove]').forEach(function (btn) {
      btn.onclick = function () {
        var si = parseInt(btn.getAttribute('data-spell-remove'), 10);
        f.spellBookRows = readSpellRowsFromDom();
        f.spellBookRows.splice(si, 1);
        if (f.spellBookRows.length < 1) f.spellBookRows.push({});
        renderAll(f);
      };
    });

    editForm.querySelectorAll('[data-img]').forEach(function (el) {
      var fid = el.dataset.img;
      el.onclick = function () {
        var up = editForm.querySelector('[data-img-upload="' + fid + '"]');
        if (up) up.click();
      };
    });

    editForm.querySelectorAll('[data-img-upload]').forEach(function (el) {
      var fid = el.dataset.imgUpload;
      el.onchange = function (ev) {
        var file = ev.target.files[0];
        if (!file || file.size > 2000000) {
          if (file) toast(t('imageTooBig') || '', true);
          return;
        }
        var formData = new FormData();
        formData.append('file', file);
        fetch(api('/api/extensions/character-sheet/upload'), { method: 'POST', body: formData, credentials: 'include' })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            if (data.ok) {
              f[fid] = data.url;
              toast(t('uploadSuccess') || '');
              renderAll(f);
            } else {
              toast((t('uploadFailed') || '') + ': ' + (data.text || ''), true);
            }
          })
          .catch(function () {
            toast(t('uploadError') || '', true);
          });
      };
    });
  };
})();
