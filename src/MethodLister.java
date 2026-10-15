import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.InputStreamReader;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodNode;

/**
 * Batch version of MethodExtractor: reads .class file paths on stdin (one per line)
 * and prints one line per method:
 *
 *   dotted.ClassName \t methodName+descriptor \t flags
 *
 * flags is a comma-separated subset of:
 *   private, protected, public, static, abstract, native, synthetic, bridge, clinit, interface
 *
 * Constructors (<init>) are skipped, as in MethodExtractor.
 */
public class MethodLister {

    public static void main(String[] args) throws Exception {
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in));
        String path;
        while ((path = in.readLine()) != null) {
            path = path.trim();
            if (path.isEmpty()) continue;
            ClassNode cn = new ClassNode();
            try (FileInputStream fis = new FileInputStream(path)) {
                new ClassReader(fis).accept(cn, ClassReader.SKIP_CODE);
            } catch (Exception e) {
                System.err.println("SKIP unreadable class " + path + ": " + e);
                continue;
            }
            String className = cn.name.replace('/', '.');
            boolean isInterface = (cn.access & Opcodes.ACC_INTERFACE) != 0;
            for (MethodNode m : cn.methods) {
                if (m.name.equals("<init>")) continue;
                StringBuilder f = new StringBuilder();
                add(f, (m.access & Opcodes.ACC_PRIVATE) != 0, "private");
                add(f, (m.access & Opcodes.ACC_PROTECTED) != 0, "protected");
                add(f, (m.access & Opcodes.ACC_PUBLIC) != 0, "public");
                add(f, (m.access & Opcodes.ACC_STATIC) != 0, "static");
                add(f, (m.access & Opcodes.ACC_ABSTRACT) != 0, "abstract");
                add(f, (m.access & Opcodes.ACC_NATIVE) != 0, "native");
                add(f, (m.access & Opcodes.ACC_SYNTHETIC) != 0, "synthetic");
                add(f, (m.access & Opcodes.ACC_BRIDGE) != 0, "bridge");
                add(f, m.name.equals("<clinit>"), "clinit");
                add(f, isInterface, "interface");
                System.out.println(className + "\t" + m.name + m.desc + "\t" + f);
            }
        }
    }

    private static void add(StringBuilder sb, boolean cond, String flag) {
        if (!cond) return;
        if (sb.length() > 0) sb.append(',');
        sb.append(flag);
    }
}
