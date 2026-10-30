package demo;

public class NameCheck {
    public boolean valid(String name) {
        String s = name;
        int min = 2;
        if (s == null) {
            return false;
        }
        boolean present = true;
        int n = s.length();
        return present && n >= min;
    }
}
