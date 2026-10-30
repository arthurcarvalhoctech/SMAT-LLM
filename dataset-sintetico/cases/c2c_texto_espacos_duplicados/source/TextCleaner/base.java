package demo;

public class TextCleaner {
    public String text = "the the  dog # note";

    public void removeComments() {
        text = text.replaceAll("\\s*#.*$", "");
    }

    public void normalizeWhitespace() {
        text = text.replaceAll("\\s+", " ").trim();
    }

    public void removeDuplicateWords() {
        String[] tokens = text.split(" ", -1);
        String last = null;
        for (int i = 0; i < tokens.length; i++) {
            if (tokens[i].isEmpty()) {
                continue;
            }
            if (tokens[i].equals(last)) {
                tokens[i] = "";
            } else {
                last = tokens[i];
            }
        }
        text = String.join(" ", tokens);
    }

    public void cleanText() {
        removeComments();
    }
}
