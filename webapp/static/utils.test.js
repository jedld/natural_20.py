/**
 * Tests for utils.js movement-path grid helpers.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { JSDOM } = require('jsdom');

function loadUtils(dom) {
  const $ = require('jquery')(dom.window);
  const sandbox = {
    window: dom.window,
    document: dom.window.document,
    $,
    jQuery: $,
    console,
    setTimeout,
    clearTimeout,
    requestAnimationFrame: (cb) => { cb(); return 0; },
    cancelAnimationFrame: () => {},
    pageXOffset: 0,
    pageYOffset: 0,
    alert: () => {},
    ajaxPost: () => {},
    ajaxGet: () => {},
    clearMovePathCache: () => {},
  };
  vm.createContext(sandbox);
  let utilsSrc = fs.readFileSync(path.join(__dirname, 'utils.js'), 'utf8');
  utilsSrc = utilsSrc.replace(/\n\$\(document\)\.ready[\s\S]*$/m, '\n');
  vm.runInContext(utilsSrc + ';\nthis.Utils = Utils;', sandbox);
  return sandbox.Utils;
}

describe('Utils movement grid origin', () => {
  test('uses displayed tile size from getBoundingClientRect (zoom-safe)', () => {
    const dom = new JSDOM(`
      <div class="image-container">
        <div class="tiles-container" data-tile-size="50">
          <div class="tile" data-coords-x="0" data-coords-y="0"></div>
        </div>
      </div>
    `, { url: 'http://localhost/' });

    const container = dom.window.document.querySelector('.tiles-container');
    const tile = dom.window.document.querySelector('.tile');

    container.getBoundingClientRect = () => ({
      left: 100,
      top: 200,
      right: 900,
      bottom: 800,
      width: 800,
      height: 600,
      x: 100,
      y: 200,
      toJSON: () => ({}),
    });
    tile.getBoundingClientRect = () => ({
      left: 150,
      top: 250,
      right: 230,
      bottom: 330,
      width: 80,
      height: 80,
      x: 150,
      y: 250,
      toJSON: () => ({}),
    });

    const Utils = loadUtils(dom);
    Utils.invalidateMovementGridCache();
    const grid = Utils._getMovementGridOrigin();

    expect(grid).not.toBeNull();
    expect(grid.tile).toBe(80);
    expect(grid.ox).toBe(100 + 80);
    expect(grid.oy).toBe(200 + 80);
  });

  test('tile center math matches scaled grid step', () => {
    const dom = new JSDOM(`
      <div class="tiles-container" data-tile-size="50">
        <div class="tile" data-coords-x="0" data-coords-y="0"></div>
      </div>
    `, { url: 'http://localhost/' });

    const container = dom.window.document.querySelector('.tiles-container');
    const tile = dom.window.document.querySelector('.tile');
    container.getBoundingClientRect = () => ({
      left: 0, top: 0, width: 400, height: 400, right: 400, bottom: 400, x: 0, y: 0, toJSON: () => ({}),
    });
    tile.getBoundingClientRect = () => ({
      left: 64, top: 64, width: 64, height: 64, right: 128, bottom: 128, x: 64, y: 64, toJSON: () => ({}),
    });

    const Utils = loadUtils(dom);
    Utils.invalidateMovementGridCache();
    const grid = Utils._getMovementGridOrigin();
    const half = grid.tile / 2;
    const center10 = { x: grid.ox + 1 * grid.tile + half, y: grid.oy + 0 * grid.tile + half };
    expect(center10.x).toBe(64 + 64 + 32);
    expect(center10.y).toBe(64 + 32);
  });
});
