package demo;

public class Checkout {
    public int amount = 40;
    public int used = 4;
    public int cap = 9;
    public int incoming = 0;
    public int total;
    public boolean hasRoom;

    private int round(int v) {
        return v;
    }

    public void compute() {
        total = amount;
        hasRoom = used + incoming <= cap;
        total = round(total);
    }
}
