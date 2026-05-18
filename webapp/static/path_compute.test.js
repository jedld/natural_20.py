const path = require('path');
const { PathCompute, PathfindingCostMap } = require('./path_compute.js');

const vectors = require(path.resolve(__dirname, '../../tests/fixtures/path_compute_vectors.json'));

function pathKey(p) {
  if (!p) return 'null';
  return p.map((pt) => `${pt[0]},${pt[1]}`).join('>');
}

function pathMoveCost(costMap, path) {
  if (!path || path.length < 2) {
    return 0;
  }
  const pc = new PathCompute(costMap);
  let total = 0;
  for (let i = 1; i < path.length; i++) {
    total += pc._baseMoveCost(path[i][0], path[i][1], path[i - 1]);
  }
  return total;
}

function pathsEquivalent(costMap, actual, expected) {
  if (pathKey(actual) === pathKey(expected)) {
    return true;
  }
  if (!actual || !expected) {
    return false;
  }
  const a0 = actual[0];
  const e0 = expected[0];
  const aN = actual[actual.length - 1];
  const eN = expected[expected.length - 1];
  if (a0[0] !== e0[0] || a0[1] !== e0[1] || aN[0] !== eN[0] || aN[1] !== eN[1]) {
    return false;
  }
  return pathMoveCost(costMap, actual) === pathMoveCost(costMap, expected);
}

describe('PathCompute (client)', () => {
  vectors.cases.forEach((tc) => {
    if (tc.name === 'multi_destinations') {
      test('multi destination paths match golden vectors', () => {
        const pc = new PathCompute(PathfindingCostMap.fromSnapshot(tc.snapshot));
        Object.entries(tc.paths).forEach(([destKey, expected]) => {
          const [dx, dy] = destKey.split(',').map(Number);
          const actual = pc.computePath(tc.source[0], tc.source[1], dx, dy);
          const costMap = PathfindingCostMap.fromSnapshot(tc.snapshot);
          expect(pathsEquivalent(costMap, actual, expected)).toBe(true);
        });
      });
      return;
    }

    test(`computePath matches Python: ${tc.name}`, () => {
      const pc = new PathCompute(PathfindingCostMap.fromSnapshot(tc.snapshot));
      const opts = {};
      if (tc.door_navigation) {
        opts.door_navigation = true;
      }
      if (tc.available_movement_cost != null) {
        opts.available_movement_cost = tc.available_movement_cost;
      }
      if (tc.accumulated_path) {
        opts.accumulated_path = tc.accumulated_path;
      }
      const actual = pc.computePath(
        tc.source[0],
        tc.source[1],
        tc.destination[0],
        tc.destination[1],
        opts
      );
      const costMap = PathfindingCostMap.fromSnapshot(tc.snapshot);
      expect(pathsEquivalent(costMap, actual, tc.expected_path)).toBe(true);
    });
  });

  test('PathfindingCostMap.fromTiles builds grid from DOM tiles', () => {
    const { JSDOM } = require('jsdom');
    const dom = new JSDOM(`
      <motion.div class="tile" data-coords-x="0" data-coords-y="0" data-difficult="False" data-blocked="False"></motion.div>
      <motion.div class="tile" data-coords-x="1" data-coords-y="0" data-difficult="False" data-blocked="False"></motion.div>
      <motion.div class="tile" data-coords-x="0" data-coords-y="1" data-difficult="True" data-blocked="False"></motion.div>
      <motion.div class="tile" data-coords-x="1" data-coords-y="1" data-difficult="False" data-blocked="True"></motion.div>
    `);
    const costMap = PathfindingCostMap.fromTiles(dom.window.document.querySelectorAll('.tile'));
    expect(costMap).not.toBeNull();
    expect(costMap.width).toBe(2);
    expect(costMap.height).toBe(2);
    expect(costMap.difficult[0]).toBe(false);
    expect(costMap.difficult[2]).toBe(true);
    expect(costMap.blocked[3]).toBe(true);
  });
});
