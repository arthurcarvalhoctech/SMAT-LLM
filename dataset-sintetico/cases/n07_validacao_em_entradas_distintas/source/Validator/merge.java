package demo;

public class Validator {
    public boolean valid(String name) {
        String s = name == null ? null : name.trim();
        int min = 2;
        if (s == null) {
            return false;
        }
        boolean present = true;
        int n = s.length();
        return present && n >= min;
    }
}
