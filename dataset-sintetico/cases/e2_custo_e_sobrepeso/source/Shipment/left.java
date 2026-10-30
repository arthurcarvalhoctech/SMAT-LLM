package demo;

public class Shipment {
    public int weight = 60;
    public int tag = 0;
    public int extra = 40;
    public int cost;
    public boolean oversize;

    public void plan(int base) {
        int p = base;
        p = p + 10;
        boolean vip = base > 50;
        if (vip) {
            p = p - 5;
        }
        cost = p;
        oversize = weight + extra > 100;
    }
}
