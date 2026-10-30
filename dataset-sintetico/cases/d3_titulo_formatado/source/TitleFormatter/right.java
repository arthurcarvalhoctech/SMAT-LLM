package demo;

public class TitleFormatter {
    public String title(String name) {
        String t = name;
        int n = t.length();
        t = t + " (draft)";
        return t;
    }
}
