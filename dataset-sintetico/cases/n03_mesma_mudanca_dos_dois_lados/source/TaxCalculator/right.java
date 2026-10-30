package demo;

public class TaxCalculator {
    public int rate = 20;
    public int tax;
    public int net;

    public void apply(int gross) {
        tax = gross * rate / 100;
        net = gross - tax;
    }
}
