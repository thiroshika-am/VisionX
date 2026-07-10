import pytest
from ai_modules.interactive_assistant import InteractiveAssistant

def test_intent_classification():
    assistant = InteractiveAssistant()
    
    assert assistant._classify_query("is there a supermarket nearby") == "find_place"
    assert assistant._classify_query("find a pharmacy") == "find_place"
    assert assistant._classify_query("is anyone near me") == "find_person"
    assert assistant._classify_query("where is my water bottle") == "find_object"
    assert assistant._classify_query("what is the tablet name") == "read_text"
    assert assistant._classify_query("read this prescription") == "read_text"
    assert assistant._classify_query("is the path clear") == "path_check"
    assert assistant._classify_query("what am i holding") == "identify"
    assert assistant._classify_query("what is this") == "identify"

def test_place_keywords():
    assistant = InteractiveAssistant()
    
    def get_place(q):
        for p, kw in assistant.place_keywords.items():
            if any(k in q for k in kw):
                return p
        return None
        
    assert get_place("find an atm") == "bank"
    assert get_place("is there a medical store") == "pharmacy"
    assert get_place("looking for a toilet") == "public_restroom"

def test_object_keywords():
    assistant = InteractiveAssistant()
    
    def get_obj(q):
        for o, kw in assistant.object_keywords.items():
            if any(k in q for k in kw):
                return o
        return None
        
    assert get_obj("where is my cell phone") == "cell phone"
    assert get_obj("find my bag") == "backpack"
    assert get_obj("is there a seat") == "chair"
