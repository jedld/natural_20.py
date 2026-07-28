from natural20.utils.conversation import parse_player_conversation_input


def test_parse_asterisk_actions():
    parsed = parse_player_conversation_input('*touches her hand gently*')
    assert parsed['spoken'] == ''
    assert parsed['actions'] == ['touches her hand gently']


def test_parse_mixed_speech_and_actions():
    parsed = parse_player_conversation_input('Hello there *offers a warm smile* how are you?')
    assert parsed['spoken'] == 'Hello there how are you?'
    assert parsed['actions'] == ['offers a warm smile']


def test_parse_action_tag_and_slash_emote():
    parsed = parse_player_conversation_input('[action: bows politely]')
    assert parsed['spoken'] == ''
    assert parsed['actions'] == ['bows politely']

    parsed = parse_player_conversation_input('/me leans against the bar')
    assert parsed['spoken'] == ''
    assert parsed['actions'] == ['leans against the bar']


def test_parse_plain_speech_unchanged():
    parsed = parse_player_conversation_input('Could I have an ale, please?')
    assert parsed['spoken'] == 'Could I have an ale, please?'
    assert parsed['actions'] == []


def test_sanitize_spoken_text_for_tts_strips_emphasis_markers():
    from natural20.utils.conversation import sanitize_spoken_text_for_tts

    assert sanitize_spoken_text_for_tts('Oh, you want the *real* news?') == 'Oh, you want the real news?'
    assert sanitize_spoken_text_for_tts('That is **very** important.') == 'That is very important.'
    assert sanitize_spoken_text_for_tts('A _little_ louder, please.') == 'A little louder, please.'
    assert sanitize_spoken_text_for_tts('Use the `scroll` now.') == 'Use the scroll now.'
