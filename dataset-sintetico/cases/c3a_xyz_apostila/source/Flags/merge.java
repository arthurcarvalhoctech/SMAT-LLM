package demo;

public class Flags {
    public int x = 1;
    public int z;
    public int y = 1;

    public void run() {
        if (x + y > 1) {
            z = 1;
        } else {
            z = 0;
        }
    }
}
