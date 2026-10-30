package demo;

public class Invoice {
    public int amount = 40;
    public int total;

    private int round(int v) {
        return v;
    }

    public void compute() {
        total = amount + 5;
        total = round(total);
    }
}
