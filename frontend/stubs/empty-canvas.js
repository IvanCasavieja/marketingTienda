// konva soporta opcionalmente node-canvas para renderizar del lado del
// servidor; no lo usamos (Canvas.tsx solo dibuja despues del mount client-side,
// ver el guard "if (!mounted)") asi que ni siquiera esta instalado. Este stub
// solo existe para que el bundler pueda resolver el require("canvas") de
// konva/lib/index-node.js durante el analisis de SSR sin que la libreria real
// se ejecute nunca de verdad.
module.exports = {};
