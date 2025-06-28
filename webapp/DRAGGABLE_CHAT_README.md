# Draggable AI Chat Panel

## Overview

The AI Chat Panel is now a draggable, floating interface that can be moved around the screen and positioned anywhere the user prefers. This provides a much more convenient way to interact with the AI assistant without needing to open a modal dialog.

## Features

### 🎯 **Draggable Interface**
- Click and drag the header (blue area) to move the panel around the screen
- Panel stays within viewport bounds automatically
- Smooth dragging with visual feedback

### 🔄 **Toggle Functionality**
- Click the chat button (top-right corner) to show/hide the panel
- Button changes color to indicate panel state (blue = hidden, green = visible)

### 📦 **Minimize/Maximize**
- Click the minus button to minimize the panel (shows only header)
- Click the plus button to restore the panel
- Minimized panel takes up less screen space

### ❌ **Close Button**
- Click the X button to close the panel completely
- Panel can be reopened with the toggle button

### 💾 **Position Memory**
- Panel position is automatically saved to localStorage
- Position is restored when the page is refreshed
- Works across browser sessions

### 📱 **Responsive Design**
- Panel adapts to different screen sizes
- Mobile-friendly with adjusted positioning
- Maintains usability on smaller screens

## Usage

### Basic Operation

1. **Open the Panel**: Click the chat button (💬) in the top-right corner
2. **Move the Panel**: Click and drag the blue header area to reposition
3. **Minimize**: Click the minus (-) button to minimize
4. **Close**: Click the X button to close completely

### AI Configuration

The panel includes the same AI configuration options as the modal:

- **Provider Selection**: Choose between Mock, OpenAI, Anthropic, or Ollama
- **API Key/URL**: Enter your API key or Ollama URL
- **Model Selection**: Choose from available models (when applicable)
- **Initialize**: Click to start the AI assistant

### Chat Interface

- **Message Input**: Type your questions in the text field
- **Send**: Click the send button or press Enter
- **Clear**: Clear the chat history
- **Context**: Get current game context information

## Technical Implementation

### CSS Classes

```css
.draggable-panel          /* Base draggable panel styles */
.draggable-panel.dragging /* Visual feedback during drag */
#ai-chat-panel           /* Specific chat panel styles */
#toggle-ai-chat          /* Toggle button styles */
```

### JavaScript Features

- **Drag Detection**: Prevents drag when clicking buttons
- **Boundary Constraints**: Keeps panel within viewport
- **Position Persistence**: Saves/loads position from localStorage
- **Window Resize Handling**: Repositions panel if needed
- **Smooth Animations**: CSS transitions for better UX

### Key Functions

```javascript
setTranslate(xPos, yPos, element)    // Move panel with constraints
savePanelPosition()                   // Save to localStorage
loadPanelPosition()                   // Load from localStorage
```

## Browser Compatibility

- ✅ Chrome/Chromium
- ✅ Firefox
- ✅ Safari
- ✅ Edge
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)

## Customization

### Styling

The panel appearance can be customized by modifying the CSS variables:

```css
#ai-chat-panel {
    min-width: 350px;      /* Minimum width */
    min-height: 400px;     /* Minimum height */
    max-width: 600px;      /* Maximum width */
    max-height: 80vh;      /* Maximum height */
}
```

### Position

Default position can be changed in the HTML:

```html
<div id="ai-chat-panel" style="top: 100px; right: 20px;">
```

### Z-Index

The panel uses z-index 1000 by default. Adjust if needed for your layout:

```css
#ai-chat-panel {
    z-index: 1000;
}
```

## Troubleshooting

### Panel Won't Move
- Make sure you're clicking on the header area (blue gradient)
- Check that you're not clicking on buttons
- Verify JavaScript is enabled

### Position Not Saved
- Check browser localStorage support
- Ensure no browser extensions are blocking localStorage
- Try refreshing the page

### Panel Disappears
- Check if the panel was moved off-screen
- Try refreshing the page to reset position
- Use browser dev tools to inspect element positioning

### Mobile Issues
- Panel may behave differently on touch devices
- Consider using the minimized state on small screens
- Test with different mobile browsers

## Future Enhancements

Potential improvements for future versions:

- **Snap to Edges**: Auto-snap to screen edges
- **Multiple Panels**: Support for multiple draggable panels
- **Custom Themes**: User-selectable color schemes
- **Keyboard Shortcuts**: Hotkeys for show/hide/minimize
- **Panel Groups**: Organize multiple panels together
- **Export/Import Settings**: Save panel configurations

## Testing

Use the test file `test_draggable_chat.html` to verify functionality:

```bash
# Open in browser
open test_draggable_chat.html
```

The test page includes:
- Visual test results
- Functionality verification
- Interactive examples
- Performance testing

## Integration

The draggable chat panel is fully integrated with the existing AI handler system:

- Uses the same `LLMHandler` class
- Maintains session logging
- Supports all AI providers
- Preserves conversation history
- Includes processing indicators

No changes to the backend are required - this is purely a frontend enhancement. 