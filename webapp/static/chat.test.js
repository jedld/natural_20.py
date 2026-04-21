const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { JSDOM } = require('jsdom');

function createMiniQuery(windowObject) {
  const documentObject = windowObject.document;
  const eventRegistry = new WeakMap();

  const normalizeEventName = (eventName) => `${eventName || ''}`.split('.')[0];

  const getHandlers = (element) => {
    let handlers = eventRegistry.get(element);
    if (!handlers) {
      handlers = {};
      eventRegistry.set(element, handlers);
    }
    return handlers;
  };

  const wrap = (elements) => {
    const api = {
      length: elements.length,
      on(eventName, handler) {
        const normalized = normalizeEventName(eventName);
        elements.forEach((element) => {
          const handlers = getHandlers(element);
          handlers[normalized] = handlers[normalized] || [];
          handlers[normalized].push(handler);
        });
        return api;
      },
      trigger(eventName) {
        const normalized = normalizeEventName(eventName);
        elements.forEach((element) => {
          const handlers = getHandlers(element)[normalized] || [];
          handlers.forEach((handler) => handler.call(element, { type: normalized, target: element }));
        });
        return api;
      },
      css(value, maybeValue) {
        if (typeof value === 'string' && typeof maybeValue === 'undefined') {
          return elements[0] ? elements[0].style[value] : undefined;
        }
        const updates = typeof value === 'string' ? { [value]: maybeValue } : (value || {});
        elements.forEach((element) => {
          Object.entries(updates).forEach(([key, cssValue]) => {
            element.style[key] = cssValue;
          });
        });
        return api;
      },
      toggleClass(className, state) {
        elements.forEach((element) => {
          element.classList.toggle(className, state);
        });
        return api;
      },
      removeClass(className) {
        elements.forEach((element) => element.classList.remove(className));
        return api;
      },
      addClass(className) {
        elements.forEach((element) => element.classList.add(className));
        return api;
      },
      attr(name, attrValue) {
        if (typeof attrValue === 'undefined') {
          return elements[0] ? elements[0].getAttribute(name) : undefined;
        }
        elements.forEach((element) => element.setAttribute(name, attrValue));
        return api;
      },
      find(selector) {
        const found = elements.flatMap((element) => Array.from(element.querySelectorAll(selector)));
        return wrap(found);
      },
      empty() {
        elements.forEach((element) => {
          element.innerHTML = '';
        });
        return api;
      },
      hide() {
        return api.css('display', 'none');
      },
      show() {
        return api.css('display', 'block');
      },
      text(textValue) {
        if (typeof textValue === 'undefined') {
          return elements[0] ? elements[0].textContent : '';
        }
        elements.forEach((element) => {
          element.textContent = textValue;
        });
        return api;
      },
      outerWidth() {
        if (!elements[0]) {
          return 0;
        }
        return parseInt(elements[0].style.width || '360', 10) || 360;
      },
      outerHeight() {
        if (!elements[0]) {
          return 0;
        }
        return parseInt(elements[0].style.height || '430', 10) || 430;
      },
      offset() {
        if (!elements[0]) {
          return { left: 0, top: 0 };
        }
        return {
          left: parseInt(elements[0].style.left || '0', 10) || 0,
          top: parseInt(elements[0].style.top || '0', 10) || 0,
        };
      },
    };

    elements.forEach((element, index) => {
      api[index] = element;
    });

    return api;
  };

  const miniQuery = (target) => {
    if (target === windowObject) {
      return wrap([windowObject]);
    }
    if (Array.isArray(target)) {
      return wrap(target);
    }
    if (target && target.nodeType) {
      return wrap([target]);
    }
    if (typeof target === 'string') {
      return wrap(Array.from(documentObject.querySelectorAll(target)));
    }
    return wrap([]);
  };

  return miniQuery;
}

describe('chat.js local conversation minimize behavior', () => {
  let dom;
  let Chat;
  let context;

  const loadChat = () => {
    const html = `<!doctype html><html><body>
      <div id="localConversationPanel" class="local-conversation-panel">
        <div class="local-conversation-header">
          <div class="local-conversation-header-main"></div>
        </div>
      </div>
      <button id="localConversationMinimize" title="Minimize local chat"><i class="glyphicon glyphicon-minus"></i></button>
      <span id="localConversationUnreadBadge">0</span>
      <div id="localConversationMentionSuggestions"></div>
    </body></html>`;

    dom = new JSDOM(html, { url: 'http://localhost/' });
    global.window = dom.window;
    global.document = dom.window.document;
    global.navigator = dom.window.navigator;

    const miniQuery = createMiniQuery(dom.window);
    global.$ = miniQuery;
    global.jQuery = miniQuery;
    dom.window.$ = miniQuery;
    dom.window.jQuery = miniQuery;

    global.localStorage = {
      getItem: jest.fn(() => null),
      setItem: jest.fn(),
    };
    dom.window.localStorage = global.localStorage;

    global.setInterval = jest.fn(() => 0);
    global.clearInterval = jest.fn();

    const sandbox = {
      window: dom.window,
      document: dom.window.document,
      navigator: dom.window.navigator,
      console: global.console,
      $: miniQuery,
      jQuery: miniQuery,
      localStorage: global.localStorage,
      setInterval: global.setInterval,
      clearInterval: global.clearInterval,
    };

    context = vm.createContext(sandbox);
    const localConversationPath = path.resolve(__dirname, 'js/local_conversation.js');
    const localConversationCode = fs.readFileSync(localConversationPath, 'utf8');
    new vm.Script(localConversationCode, { filename: localConversationPath }).runInContext(context);
    const chatPath = path.resolve(__dirname, 'js/chat.js');
    const chatCode = fs.readFileSync(chatPath, 'utf8');
    new vm.Script(chatCode, { filename: chatPath }).runInContext(context);
    Chat = new vm.Script('(typeof Chat !== "undefined") ? Chat : undefined').runInContext(context);
  };

  beforeEach(() => {
    loadChat();
  });

  test('applyLocalConversationPanelPosition keeps compact geometry while minimized', () => {
    Chat.localConversation.minimized = true;

    Chat.applyLocalConversationPanelPosition({ left: 111, top: 222 });

    const panel = dom.window.document.getElementById('localConversationPanel');
    expect(panel.style.right).toBe('240px');
    expect(panel.style.bottom).toBe('20px');
    expect(panel.style.width).toBe('260px');
    expect(panel.style.height).toBe('auto');
    expect(panel.style.left === '' || panel.style.left === 'auto').toBe(true);
    expect(panel.style.top === '' || panel.style.top === 'auto').toBe(true);
  });

  test('setLocalConversationMinimized reapplies compact layout after stale dimensions linger', () => {
    const panel = global.$('#localConversationPanel');
    panel.css({ width: '800px', height: '500px', left: '10px', top: '10px', right: 'auto', bottom: 'auto' });

    Chat.setLocalConversationMinimized(true);

    expect(panel[0].style.right).toBe('240px');
    expect(panel[0].style.bottom).toBe('20px');
    expect(panel[0].style.width).toBe('260px');
    expect(panel[0].style.height).toBe('auto');
    expect(panel[0].style.left === '' || panel[0].style.left === 'auto').toBe(true);
    expect(panel[0].style.top === '' || panel[0].style.top === 'auto').toBe(true);
  });
});