package demo;

public class Limiter {
    public int allowed(int requests) {
        int limit = 10;
        if (requests > limit) {
            return limit;
        }
        return requests > 0 ? requests : 0;
    }
}
