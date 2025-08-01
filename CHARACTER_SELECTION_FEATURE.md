# Character Selection Feature Implementation

## Overview
This implementation adds a character selection page for users who don't have a default controller assigned to them. The feature includes:

1. **Character Selection Page**: A D&D themed page that shows available characters
2. **Customizable Background**: Separate background image configuration for character selection
3. **Character Status**: Visual indicators for available/taken/selected characters
4. **Seamless Integration**: Automatic redirection flow from login to character selection when needed

## Configuration

### New Configuration Option in index.json
```json
{
  "character_selection_background": "goblin_ambush.png"
}
```

- **character_selection_background**: (optional) Specifies the background image for the character selection page
- If not specified, falls back to using the `login_background` image
- Image should be placed in the `templates/assets/` directory

### Example Configuration
```json
{
  "title": "The Goblin Ambush",
  "login_background": "goblin_ambush_login.png",
  "character_selection_background": "goblin_ambush.png",
  "selectable_characters": [
    {
      "name": "gomerin",
      "file": "characters/gomerin.png",
      "description": "A brave warrior with a heart of gold."
    }
  ]
}
```

## User Flow

1. **User logs in** → Login page validates credentials
2. **Check for assigned characters** → System checks if user has any controllers assigned
3. **Redirect accordingly**:
   - If user has characters: Go to main game interface
   - If user has no characters: Go to character selection page
   - If user is DM: Go directly to main interface

## Features

### Character Selection Page
- **D&D Themed Design**: Medieval fantasy styling with appropriate fonts and colors
- **Character Cards**: Display character portrait, name, and description
- **Status Indicators**: 
  - Available (green)
  - Taken (red) 
  - Selected (gold)
- **Responsive Design**: Works on desktop and mobile devices

### Backend Integration
- **Session Management**: Maintains user session throughout the flow
- **Controller Assignment**: Automatically assigns selected character to user
- **Validation**: Prevents selection of already taken characters
- **Error Handling**: Graceful error messages for various failure scenarios

## New Routes Added

### `/character_selection` (GET)
- Shows the character selection page
- Redirects to main page if user already has characters
- Displays available characters and their status

### `/select_character` (POST)
- Handles character selection submission
- Validates character availability
- Updates controller assignments
- Returns JSON response for AJAX handling

### Updated Routes

#### `/login` (POST)
- Added character selection check
- Returns `character_selection_required` status when user needs to select a character

#### `/` (GET) - Main index
- Added character selection redirect logic
- Improved error handling for users without characters

#### `/logout` (GET/POST)
- Extended to support GET requests for character selection page logout

## Technical Implementation

### Backend Changes (app.py)
1. Added `CHARACTER_SELECTION_BACKGROUND` configuration loading
2. New route handlers for character selection workflow
3. Enhanced login flow with character checking
4. Improved index route with proper redirects and error handling

### Frontend Changes
1. **character_selection.html**: New template with D&D themed styling
2. **login.html**: Updated JavaScript to handle character selection redirect
3. **Responsive design**: Mobile-friendly character selection interface

### CSS Features
- **D&D Typography**: Uses 'Cinzel' and 'Uncial Antiqua' fonts
- **Medieval Color Scheme**: Gold, brown, and cream colors
- **Interactive Elements**: Hover effects and smooth transitions
- **Visual Feedback**: Clear selection states and loading indicators

## Testing

### Test Users
Users without default controllers (perfect for testing):
- keo / keo
- jm / jm  
- leandro / leandro
- party / party

### Test Scenarios
1. Login with user without assigned character → Should see character selection
2. Select available character → Should assign and redirect to main game
3. Try to select taken character → Should show error message
4. Login with user who already has character → Should go directly to main game
5. DM login → Should bypass character selection entirely

## Future Enhancements

### Possible Improvements
1. **Character Portraits**: Add proper character portrait images in `templates/assets/characters/`
2. **Character Details**: Extended character information (stats, abilities, etc.)
3. **Character Creation**: Allow users to create custom characters
4. **Session Persistence**: Remember character selections across sessions
5. **Admin Interface**: DM tools to manage character assignments
6. **Multiple Characters**: Allow users to control multiple characters

### Asset Management
- Character images are currently using token images with fallback
- For better visual experience, add character portraits to `templates/assets/characters/`
- Background images should be placed in `templates/assets/`

## Configuration Examples

### Basic Setup (Same background for login and character selection)
```json
{
  "login_background": "fantasy_tavern.png"
}
```

### Different Backgrounds
```json
{
  "login_background": "castle_gates.png",
  "character_selection_background": "heroes_hall.png"
}
```

### No Character Selection Background (uses login background)
```json
{
  "login_background": "dungeon_entrance.png"
}
```
