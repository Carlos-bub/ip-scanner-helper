'use strict';

// Geometry only. Relationships and group memberships come from the domain.
function layoutTopologyGroups(groups, availableWidth) {
  const width = Math.max(320, availableWidth), margin = 20, gap = 20;
  const columns = Math.max(1, Math.min(3, Math.floor((width - margin * 2 + gap) / 380)));
  const groupWidth = (width - margin * 2 - gap * (columns - 1)) / columns;
  const placements = [];
  let y = margin;
  for (let start = 0; start < groups.length; start += columns) {
    const row = groups.slice(start, start + columns).map((group, column) => {
      const cardColumns = Math.max(1, Math.floor((groupWidth - 32 + 10) / 164));
      const cardWidth = (groupWidth - 32 - (cardColumns - 1) * 10) / cardColumns;
      const headerHeight = group.context_ids.length ? 120 : 94;
      const rows = Math.ceil(group.visible_ids.length / cardColumns);
      const height = group.open ? headerHeight + rows * 64 + 48 : 112;
      const x = margin + column * (groupWidth + gap);
      return {group, x, y, width: groupWidth, height, headerHeight,
        cards: group.open ? group.visible_ids.map((id, index) => ({id,
          x: x + 16 + (index % cardColumns) * (cardWidth + 10),
          y: y + headerHeight + Math.floor(index / cardColumns) * 64,
          width: cardWidth, height: 54})) : []};
    });
    placements.push(...row);
    y += Math.max(...row.map(item => item.height)) + gap;
  }
  return {groups: placements, width, height: Math.max(240, y)};
}

function layoutTopologyMesh(nodes, availableWidth) {
  const width = Math.max(320, availableWidth), margin = 28, top = 76, gap = 30;
  const columns = Math.max(1, Math.min(5, Math.floor((width - margin * 2 + gap) / 220)));
  const cardWidth = Math.min(190, (width - margin * 2 - gap * (columns - 1)) / columns);
  const usedWidth = columns * cardWidth + (columns - 1) * gap;
  return {width, height: Math.max(260, Math.ceil(nodes.length / columns) * 112 + top + margin),
    cards: nodes.map((node, index) => ({id: node.id,
      x: (width - usedWidth) / 2 + (index % columns) * (cardWidth + gap),
      y: top + Math.floor(index / columns) * 112, width: cardWidth, height: 54}))};
}

if (typeof module !== 'undefined') module.exports = {layoutTopologyGroups, layoutTopologyMesh};

function layoutTopologyTree(items, availableWidth, {maxColumns = 6} = {}) {
  const width = Math.max(360, availableWidth), margin = 30, gap = 24;
  const columns = Math.max(1, Math.min(maxColumns, Math.floor((width - margin * 2 + gap) / 210)));
  const cardWidth = Math.min(192, (width - margin * 2 - gap * (columns - 1)) / columns);
  const levels = new Map();
  for (const item of items) {
    if (!levels.has(item.depth)) levels.set(item.depth, []);
    levels.get(item.depth).push(item);
  }
  const cards = [];
  let y = 36;
  for (const depth of [...levels.keys()].sort((a,b) => a-b)) {
    const nodes = levels.get(depth);
    for (let start = 0; start < nodes.length; start += columns) {
      const row = nodes.slice(start, start + columns);
      const rowColumns = Math.min(nodes.length, columns);
      const rowWidth = rowColumns * cardWidth + (rowColumns - 1) * gap;
      row.forEach((item, index) => cards.push(Object.assign({}, item, {x: (width - rowWidth) / 2 + index * (cardWidth + gap),
        y, width: cardWidth, height: item.switch ? 78 : 62})));
      y += 126;
    }
    y += 28;
  }
  return {width, height: Math.max(300, y + 32), cards};
}
if (typeof module !== 'undefined') module.exports.layoutTopologyTree = layoutTopologyTree;
