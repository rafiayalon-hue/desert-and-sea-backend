"""
נוסחי ה-SMS לאורחים (גיבוי כש-WhatsApp נכשל) — זה המקום היחיד לערוך טקסט.
עברית למספר ישראלי, אנגלית לכל מספר אחר.

שדות זמינים: name, room, checkin, checkout, checkout_time, code, link, phone
"""

# שורת הוראות הגעה קצרה שנכנסת להודעת קוד הכניסה (ביום ההגעה, 10:00).
# לערוך לפי הצורך — שורה אחת, בלי קישורים ארוכים.
ARRIVAL_NOTE_HE = "חניה ליד הצימר. לשאלות אנחנו זמינים בטלפון."
ARRIVAL_NOTE_EN = "Parking next to the cabin. Call us with any question."

TEXTS = {
    "he": {
        "confirmation": (
            "שלום {name}, הזמנתכם {room} אושרה!\n"
            "כניסה {checkin} מ-14:00, יציאה {checkout}.\n"
            "נשמח לארח אתכם — מדבר וים"
        ),
        "pre_arrival": (
            "שלום {name}, עוד יומיים נפגשים!\n"
            "כניסה {checkin} מ-14:00.\n"
            "הוראות הגעה וקוד כניסה יישלחו אליכם בבוקר יום ההגעה.\n"
            "איזה חלב תרצו שנשאיר לכם? (רגיל / סויה / שיבולת שועל / שקדים / ללא לקטוז / בלי)\n"
            "— מדבר וים"
        ),
        "entry_code": (
            "בוקר טוב {name}, היום נפגשים!\n"
            "קוד הכניסה לצימר: {code} (פעיל מ-14:00)\n"
            "{arrival}\n"
            "{link}"
            "יציאה {checkout} עד {checkout_time}. טלפון: {phone}\n"
            "— מדבר וים"
        ),
        "checkout": (
            "שלום {name}, תודה שהתארחתם!\n"
            "תזכורת: יציאה היום עד {checkout_time}.\n"
            "נשמח לראותכם שוב — מדבר וים"
        ),
    },
    "en": {
        "confirmation": (
            "Hi {name}, your booking at Desert and Sea is confirmed!\n"
            "Check-in {checkin} from 14:00, check-out {checkout}.\n"
            "See you soon — Desert and Sea"
        ),
        "pre_arrival": (
            "Hi {name}, see you in two days!\n"
            "Check-in {checkin} from 14:00.\n"
            "Arrival instructions and your door code will be sent on the morning of arrival.\n"
            "Which milk would you like us to leave for you? (regular / soy / oat / almond / lactose-free / none)\n"
            "— Desert and Sea"
        ),
        "entry_code": (
            "Good morning {name}, see you today!\n"
            "Your door code: {code} (active from 14:00)\n"
            "{arrival}\n"
            "{link}"
            "Check-out {checkout} by {checkout_time}. Phone: {phone}\n"
            "— Desert and Sea"
        ),
        "checkout": (
            "Hi {name}, thank you for staying with us!\n"
            "Reminder: check-out today by {checkout_time}.\n"
            "Hope to see you again — Desert and Sea"
        ),
    },
}


def room_phrase_he(room: str) -> str:
    """'מדבר' → 'בצימר מדבר', 'מדבר וים' → 'בשני הצימרים'."""
    if room == "מדבר וים":
        return "בשני הצימרים"
    if room:
        return f"בצימר {room}"
    return ""
