package demo;

public class Counter {
    public int value;
    public int steps;

    public void increment() {
        value = value + 1;
        steps = steps + 1;
    }

    public void reset() {
        value = 0;
    }
}
