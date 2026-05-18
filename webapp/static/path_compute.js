/**
 * Client-side A* pathfinding using a precomputed cost map (see natural20/ai/pathfinding_cost_map.py).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.PathComputeModule = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : this, function () {
  const MAX_DISTANCE = 4000000;
  const DIR_OFFSETS = [
    [-1, -1], [-1, 0], [-1, 1],
    [0, -1], [0, 1],
    [1, -1], [1, 0], [1, 1],
  ];

  function dirIndex(dx, dy) {
    for (let i = 0; i < DIR_OFFSETS.length; i++) {
      if (DIR_OFFSETS[i][0] === dx && DIR_OFFSETS[i][1] === dy) {
        return i;
      }
    }
    return -1;
  }

  class PathfindingCostMap {
    constructor(snapshot) {
      this.snapshot = snapshot;
      this.width = snapshot.width;
      this.height = snapshot.height;
      this.feetPerGrid = snapshot.feet_per_grid || 5;
      const ent = snapshot.entity || {};
      this.prone = !!ent.prone;
      this.flying = !!ent.flying;
      this.difficult = snapshot.difficult || [];
      this.hazard = snapshot.hazard || [];
      this.door = snapshot.door || [];
      this.blocked = snapshot.blocked || [];
      this.passNormal = snapshot.pass_normal || [];
      this.passSqueeze = snapshot.pass_squeeze || [];
    }

    static fromSnapshot(snapshot) {
      return new PathfindingCostMap(snapshot);
    }

    /**
     * Build a simplified cost map from rendered .tile elements (walls + difficult only).
     * Passability is "not blocked" on both ends of an edge; use server snapshots for doors/entities.
     */
    static fromTiles(tileElements, options) {
      options = options || {};
      const tiles = Array.from(tileElements || []);
      if (!tiles.length) {
        return null;
      }
      let maxX = 0;
      let maxY = 0;
      const byKey = {};
      tiles.forEach((el) => {
        const x = parseInt(el.getAttribute('data-coords-x'), 10);
        const y = parseInt(el.getAttribute('data-coords-y'), 10);
        if (Number.isNaN(x) || Number.isNaN(y)) {
          return;
        }
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
        byKey[x + ',' + y] = {
          difficult: el.getAttribute('data-difficult') === 'True' || el.getAttribute('data-difficult') === 'true',
          blocked: el.getAttribute('data-blocked') === 'True' || el.getAttribute('data-blocked') === 'true',
          door: el.getAttribute('data-door') === 'True' || el.getAttribute('data-door') === 'true',
        };
      });
      const width = maxX + 1;
      const height = maxY + 1;
      const difficult = [];
      const hazard = [];
      const door = [];
      const blocked = [];
      const passNormal = [];
      const passSqueeze = [];
      const ent = options.entity || {};

      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const t = byKey[x + ',' + y] || { difficult: false, blocked: true, door: false };
          difficult.push(!!t.difficult);
          hazard.push(false);
          door.push(!!t.door);
          blocked.push(!!t.blocked);
          let pn = 0;
          let ps = 0;
          DIR_OFFSETS.forEach((off, di) => {
            const nx = x + off[0];
            const ny = y + off[1];
            if (nx < 0 || ny < 0 || nx >= width || ny >= height) {
              return;
            }
            const nt = byKey[nx + ',' + ny];
            if (!t.blocked && nt && !nt.blocked) {
              pn |= 1 << di;
              ps |= 1 << di;
            }
          });
          passNormal.push(pn);
          passSqueeze.push(ps);
        }
      }

      return new PathfindingCostMap({
        version: 1,
        width,
        height,
        feet_per_grid: options.feet_per_grid || 5,
        entity: {
          prone: !!ent.prone,
          flying: !!ent.flying,
        },
        difficult,
        hazard,
        door,
        blocked,
        pass_normal: passNormal,
        pass_squeeze: passSqueeze,
      });
    }

    _idx(x, y) {
      return y * this.width + x;
    }

    _tile(arr, x, y) {
      return !!arr[this._idx(x, y)];
    }

    _hasPass(arr, x, y, di) {
      return (arr[this._idx(x, y)] & (1 << di)) !== 0;
    }
  }

  class PathCompute {
    constructor(costMap) {
      this.costMap = costMap instanceof PathfindingCostMap
        ? costMap
        : PathfindingCostMap.fromSnapshot(costMap);
      this._allowedHazard = new Set();
    }

    _isDoor(x, y) {
      return this.costMap._tile(this.costMap.door, x, y);
    }

    _isHazard(x, y) {
      return this.costMap._tile(this.costMap.hazard, x, y);
    }

    _baseMoveCost(x, y, src) {
      let cost = this.costMap._tile(this.costMap.difficult, x, y) && !this.costMap.flying ? 2 : 1;
      if (this.costMap.prone) {
        cost += 1;
      }
      if (src && (src[0] !== x || src[1] !== y)) {
        cost += 0.1;
      }
      return cost;
    }

    _heuristic(cx, cy, dx, dy) {
      return Math.hypot(cx - dx, cy - dy);
    }

    _diagonalClear(x, y, dx, dy, allowSqueeze, doorNavigation) {
      if (Math.abs(dx) !== 1 || Math.abs(dy) !== 1) {
        return true;
      }
      const ax = x + dx;
      const ay = y;
      const bx = x;
      const by = y + dy;
      const passArr = allowSqueeze ? this.costMap.passSqueeze : this.costMap.passNormal;
      const diA = dirIndex(dx, 0);
      const diB = dirIndex(0, dy);
      let adj1 = diA >= 0 && this.costMap._hasPass(passArr, x, y, diA);
      let adj2 = diB >= 0 && this.costMap._hasPass(passArr, x, y, diB);
      if (doorNavigation) {
        if (!adj1 && this._isDoor(ax, ay)) {
          adj1 = true;
        }
        if (!adj2 && this._isDoor(bx, by)) {
          adj2 = true;
        }
      }
      return adj1 || adj2;
    }

    _getNeighbors(x, y, doorNavigation) {
      const neighbors = [];
      const cm = this.costMap;
      DIR_OFFSETS.forEach((off, di) => {
        const nx = x + off[0];
        const ny = y + off[1];
        if (nx < 0 || ny < 0 || nx >= cm.width || ny >= cm.height) {
          return;
        }
        if (this._isHazard(nx, ny) && !this._allowedHazard.has(nx + ',' + ny)) {
          return;
        }
        if (
          this._diagonalClear(x, y, off[0], off[1], false, doorNavigation) &&
          (cm._hasPass(cm.passNormal, x, y, di) || (doorNavigation && this._isDoor(nx, ny)))
        ) {
          neighbors.push([[nx, ny], this._baseMoveCost(nx, ny, [x, y])]);
        } else if (
          this._diagonalClear(x, y, off[0], off[1], true, doorNavigation) &&
          (cm._hasPass(cm.passSqueeze, x, y, di) || (doorNavigation && this._isDoor(nx, ny)))
        ) {
          let moveCost = this._baseMoveCost(nx, ny, [x, y]) + 1;
          if (cm.prone) {
            moveCost += 1;
          }
          neighbors.push([[nx, ny], moveCost]);
        }
      });
      return neighbors;
    }

    computePath(sourceX, sourceY, destinationX, destinationY, options) {
      options = options || {};
      const cm = this.costMap;
      if (sourceX < 0 || sourceY < 0 || sourceX >= cm.width || sourceY >= cm.height) {
        return null;
      }
      destinationX = Math.max(0, Math.min(destinationX, cm.width - 1));
      destinationY = Math.max(0, Math.min(destinationY, cm.height - 1));

      const distances = Array.from({ length: cm.width }, () => Array(cm.height).fill(MAX_DISTANCE));
      const parents = Array.from({ length: cm.width }, () => Array(cm.height).fill(null));
      const pq = [];

      let availableMovementCost = options.available_movement_cost;
      let initialCost = 0;
      const accumulatedPath = options.accumulated_path;
      if (accumulatedPath && accumulatedPath.length > 1) {
        for (let i = 0; i < accumulatedPath.length - 1; i++) {
          const x1 = accumulatedPath[i][0];
          const y1 = accumulatedPath[i][1];
          initialCost += this._baseMoveCost(x1, y1) * cm.feetPerGrid;
        }
      }
      if (availableMovementCost != null) {
        availableMovementCost -= initialCost;
      }

      this._allowedHazard = new Set([
        sourceX + ',' + sourceY,
        destinationX + ',' + destinationY,
      ]);
      distances[sourceX][sourceY] = 0;
      pq.push({
        f: this._heuristic(sourceX, sourceY, destinationX, destinationY),
        g: 0,
        x: sourceX,
        y: sourceY,
      });

      const doorNavigation = !!options.door_navigation;

      while (pq.length) {
        pq.sort((a, b) => a.f - b.f || a.g - b.g);
        const current = pq.shift();
        const cx = current.x;
        const cy = current.y;
        const currentG = current.g;
        if (currentG > distances[cx][cy]) {
          continue;
        }
        if (cx === destinationX && cy === destinationY) {
          break;
        }
        this._getNeighbors(cx, cy, doorNavigation).forEach(([coord, moveCost]) => {
          const nx = coord[0];
          const ny = coord[1];
          const newG = currentG + moveCost;
          if (newG < distances[nx][ny]) {
            distances[nx][ny] = newG;
            parents[nx][ny] = [cx, cy];
            const h = this._heuristic(nx, ny, destinationX, destinationY);
            pq.push({ f: newG + h, g: newG, x: nx, y: ny });
          }
        });
      }

      if (distances[destinationX][destinationY] === MAX_DISTANCE) {
        return null;
      }

      const path = [];
      let node = [destinationX, destinationY];
      while (node) {
        path.push(node);
        node = parents[node[0]][node[1]];
      }
      path.reverse();

      if (availableMovementCost != null) {
        const trimmed = [];
        for (let i = 0; i < path.length; i++) {
          const px = path[i][0];
          const py = path[i][1];
          if (distances[px][py] * cm.feetPerGrid <= availableMovementCost) {
            trimmed.push(path[i]);
          } else {
            break;
          }
        }
        return trimmed;
      }

      if (doorNavigation && path.length > 1) {
        for (let i = 1; i < path.length; i++) {
          const px = path[i][0];
          const py = path[i][1];
          if (!this._isDoor(px, py)) {
            continue;
          }
          const prev = path[i - 1];
          const pdx = px - prev[0];
          const pdy = py - prev[1];
          const di = dirIndex(pdx, pdy);
          if (di < 0 || !this.costMap._hasPass(this.costMap.passNormal, prev[0], prev[1], di)) {
            return path.slice(0, i);
          }
        }
      }

      return path;
    }
  }

  return {
    MAX_DISTANCE,
    DIR_OFFSETS,
    PathfindingCostMap,
    PathCompute,
  };
});
