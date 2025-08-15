// Polyfills for jsdom/Jest environment
const { TextEncoder, TextDecoder } = require('util');

if (typeof global.TextEncoder === 'undefined') {
  global.TextEncoder = TextEncoder;
}
if (typeof global.TextDecoder === 'undefined') {
  global.TextDecoder = TextDecoder;
}
// Provide global jQuery for engine.js which expects $ globally
const jquery = require('jquery');
const { JSDOM } = require('jsdom');

// Ensure a window exists
if (!global.window) {
  const dom = new JSDOM('<!doctype html><html><body></body></html>');
  global.window = dom.window;
  global.document = dom.window.document;
}

global.$ = jquery(global.window);
