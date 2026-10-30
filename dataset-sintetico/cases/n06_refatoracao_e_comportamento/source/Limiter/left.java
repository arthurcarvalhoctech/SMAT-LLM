package demo;

public class Limiter {
    public int allowed(int requests) {
        int limit = 5 + 5;
        if (requests > limit) {
            return limit;
        }
        return requests;
    }
}
