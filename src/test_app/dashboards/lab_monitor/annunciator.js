// A row of alarm tiles, one per subsystem. The tiles always exist; alarms
// only change their colour and text, so the layout below does not move.
export default function ({ data, parentElement }) {
  let root = parentElement.__labAnnunciator;
  if (!root) {
    root = parentElement.__labAnnunciator = document.createElement('div');
    root.className = 'annunciator';
    root.setAttribute('role', 'status');
    parentElement.appendChild(root);
  }
  while (root.children.length < data.tiles.length) {
    const tile = document.createElement('div');
    tile.className = 'tile';
    tile.innerHTML = '<span class="label"></span><span class="text"></span>';
    root.appendChild(tile);
  }
  while (root.children.length > data.tiles.length) root.lastChild.remove();
  data.tiles.forEach((tile, i) => {
    const node = root.children[i];
    node.dataset.level = tile.level;
    node.title = tile.text;
    node.querySelector('.label').textContent = tile.label;
    node.querySelector('.text').textContent = tile.text;
  });
}
