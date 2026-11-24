/* Benchmarks section: draws inline SVG charts from assets/bench/showdown-2026-11-22.json.
   No external libraries; charts resize with the window. */
(function () {
  'use strict';
  var SVG_NS = 'http://www.w3.org/2000/svg';
  var DATA_URL = 'assets/bench/showdown-2026-11-22.json';

  var IDLE_METRICS = [
    { key: 'boot_s', title: 'Boot to desktop', unit: ' s' },
    { key: 'settle_s', title: 'Settle time', unit: ' s' },
    { key: 'ram_mib', title: 'RAM', unit: ' MiB' },
    { key: 'processes', title: 'Processes', unit: '' },
    { key: 'idle_cpu_pct', title: 'CPU in use', unit: ' %' },
    { key: 'ctxt_per_s', title: 'Context switches', unit: ' /s' }
  ];

  function fmt(value) {
    if (Number.isInteger(value)) return String(value);
    return String(Math.round(value * 100) / 100);
  }

  function el(name, attrs, text) {
    var node = document.createElementNS(SVG_NS, name);
    for (var key in attrs) node.setAttribute(key, attrs[key]);
    if (text != null) node.textContent = text;
    return node;
  }

  function isSpaced(name) { return name.indexOf('Spaced') === 0; }

  /* One horizontal bar chart (lower or higher is better) inside a card. */
  function barChart(container, opts) {
    var rows = opts.rows.slice().sort(function (a, b) {
      return opts.better === 'higher' ? b.value - a.value : a.value - b.value;
    });
    var card = document.createElement('div');
    card.className = 'bench-chart';
    var h4 = document.createElement('h4');
    h4.textContent = opts.title;
    var sub = document.createElement('p');
    sub.className = 'sub';
    sub.textContent = opts.subtitle;
    card.appendChild(h4);
    card.appendChild(sub);

    var width = Math.max(300, container.clientWidth || 360);
    var rowH = 24, padTop = 6, labelW = 118, valueW = 74;
    var height = padTop + rows.length * rowH + 6;
    var max = 0;
    rows.forEach(function (r) { if (r.value > max) max = r.value; });
    var barMax = Math.max(40, width - labelW - valueW);

    var svg = el('svg', {
      viewBox: '0 0 ' + width + ' ' + height,
      role: 'img',
      'aria-label': opts.aria
    });
    rows.forEach(function (r, i) {
      var y = padTop + i * rowH;
      svg.appendChild(el('text', { x: 0, y: y + 16, 'class': 'bench-label' }, r.name));
      var w = max > 0 ? Math.max(2, Math.round(r.value / max * barMax)) : 2;
      svg.appendChild(el('rect', {
        x: labelW, y: y + 7, width: w, height: 11, rx: 3,
        'class': isSpaced(r.name) ? 'bench-spaced' : 'bench-other'
      }));
      svg.appendChild(el('text', {
        x: labelW + w + 7, y: y + 16, 'class': 'bench-value'
      }, fmt(r.value) + opts.unit));
    });
    card.appendChild(svg);
    container.appendChild(card);
    return card;
  }

  /* Heatmap: distro rows (sorted by RAM), metric columns, each column shaded best->worst. */
  function heatmap(container, distros) {
    var rows = distros.slice().sort(function (a, b) { return a.ram_mib - b.ram_mib; });
    var labelW = 130, cellW = 92, cellH = 30, headH = 26;
    var width = labelW + IDLE_METRICS.length * cellW;
    var height = headH + rows.length * cellH + 6;
    var svg = el('svg', {
      viewBox: '0 0 ' + width + ' ' + height,
      role: 'img',
      'aria-label': 'Idle benchmark heatmap: ' + rows.length + ' distros by ' +
        IDLE_METRICS.length + ' metrics. Rows are sorted by RAM, lightest cell per column is best, darkest is worst.'
    });
    IDLE_METRICS.forEach(function (m, c) {
      svg.appendChild(el('text', {
        x: labelW + c * cellW + cellW / 2, y: 17, 'text-anchor': 'middle', 'class': 'bench-label'
      }, m.title));
    });
    IDLE_METRICS.forEach(function (m, c) {
      var min = Infinity, max = -Infinity;
      rows.forEach(function (r) {
        if (r[m.key] < min) min = r[m.key];
        if (r[m.key] > max) max = r[m.key];
      });
      rows.forEach(function (r, i) {
        var t = max > min ? (r[m.key] - min) / (max - min) : 0;
        var alpha = 0.5 - t * 0.46;
        var y = headH + i * cellH;
        svg.appendChild(el('rect', {
          x: labelW + c * cellW + 3, y: y, width: cellW - 6, height: cellH - 6, rx: 4,
          fill: 'rgba(146,203,255,' + alpha.toFixed(3) + ')'
        }));
        svg.appendChild(el('text', {
          x: labelW + c * cellW + cellW / 2, y: y + 16, 'text-anchor': 'middle', 'class': 'bench-value'
        }, fmt(r[m.key])));
      });
    });
    rows.forEach(function (r, i) {
      svg.appendChild(el('text', {
        x: 0, y: headH + i * cellH + 16, 'class': isSpaced(r.distro) ? 'bench-value' : 'bench-label'
      }, r.distro));
    });
    container.appendChild(svg);
  }

  function takeaway(data) {
    var distros = data.distros;
    var fastest = distros[0], leastRam = distros[0];
    distros.forEach(function (d) {
      if (d.boot_s < fastest.boot_s) fastest = d;
      if (d.ram_mib < leastRam.ram_mib) leastRam = d;
    });
    var others = distros.filter(function (d) { return d !== fastest; })
      .sort(function (a, b) { return a.boot_s - b.boot_s; })[0];
    var ratio = others ? (others.boot_s / fastest.boot_s).toFixed(1) : null;
    var text = fastest.distro + ' boots to the desktop in ' + fmt(fastest.boot_s) + ' s' +
      (ratio ? ' (' + ratio + '\u00d7 faster than the next fastest)' : '') +
      ', and ' + (leastRam === fastest ? 'it' : leastRam.distro) + ' idles on just ' + fmt(leastRam.ram_mib) +
      ' MiB of RAM \u2014 the lowest of the ' + distros.length + ' distros measured here.';
    document.getElementById('bench-takeaway').textContent = text;
  }

  function render(data) {
    takeaway(data);
    var idle = document.getElementById('bench-idle');
    idle.textContent = '';
    IDLE_METRICS.forEach(function (m) {
      barChart(idle, {
        title: m.title,
        subtitle: 'lower is better',
        unit: m.unit,
        better: 'lower',
        aria: m.title + ' per distro, lower is better, best first.',
        rows: data.distros.map(function (d) { return { name: d.distro, value: d[m.key] }; })
      });
    });

    var heat = document.getElementById('bench-heatmap');
    heat.textContent = '';
    heatmap(heat, data.distros);
  }

  function load() {
    fetch(DATA_URL).then(function (res) {
      if (!res.ok) throw new Error('benchmarks data unavailable');
      return res.json();
    }).then(function (data) {
      render(data);
      var timer = null;
      addEventListener('resize', function () {
        clearTimeout(timer);
        timer = setTimeout(function () { render(data); }, 200);
      });
    }).catch(function (err) {
      var note = document.querySelector('.bench-note');
      if (note) note.textContent = 'Charts could not load: ' + err.message + '.';
    });
  }

  load();
})();
