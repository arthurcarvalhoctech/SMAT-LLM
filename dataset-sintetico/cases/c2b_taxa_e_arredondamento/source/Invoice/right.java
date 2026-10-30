package demo;

public class Invoice {
    public int amount = 40;
    public int total;

    private int round(int v) {
        return (v + 9) / 10 * 10;
    }

    public void compute() {
        total = amount;
        total = round(total);
    }
}
