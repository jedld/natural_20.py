
def classify(table_name):
    # Split the string into words based on underscores
    words = table_name.split('_')
    # Capitalize the first letter of each word and join them
    class_name = ''.join(word.capitalize() for word in words)
    # Remove any trailing 's' if it exists to handle plural forms
    if class_name.endswith('s'):
        class_name = class_name[:-1]
    return class_name