// Exports bounded static call paths from protocol dispatchers to component functions.
// @category TufAio

import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class ExportDispatcherCallPaths extends GhidraScript {
	private static final int MAX_DEPTH = 12;

	private static final String[][] SOURCES = {
		{"00126dfc", "device command dispatcher"},
		{"001293f8", "transport dispatcher"},
		{"0012c12c", "USB setup request dispatcher"},
		{"0012ced0", "USB event dispatcher"}
	};

	private static final String[][] TARGETS = {
		{"0010ccd0", "LCM diagnostic-string owner"},
		{"0010ee20", "emWin diagnostic-string owner"},
		{"001268d0", "boot diagnostic-string owner"},
		{"00127660", "serial-number diagnostic-string owner"},
		{"00127854", "boot/JPG path owner"},
		{"0012a5ac", "SPI-flash diagnostic-string owner"}
	};

	private static class PathNode {
		final Function function;
		final List<Function> path;

		PathNode(Function function, List<Function> path) {
			this.function = function;
			this.path = path;
		}
	}

	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length != 1) {
			throw new IllegalArgumentException("expected output file argument");
		}

		File output = new File(args[0]);
		if (output.exists()) {
			throw new IllegalStateException("refusing to overwrite " + output);
		}

		try (PrintWriter out = new PrintWriter(output, "UTF-8")) {
			out.println("PROGRAM\t" + currentProgram.getName());
			out.println("MAX_DEPTH\t" + MAX_DEPTH);
			out.println("NOTE\tOnly statically resolved calls represented by Ghidra are traversed.");
			out.println();

			for (String[] sourceSpec : SOURCES) {
				Function source = functionAt(sourceSpec[0]);
				out.printf("SOURCE\t%s\t%s\t%s%n",
					sourceSpec[0], sourceSpec[1], describe(source));

				for (String[] targetSpec : TARGETS) {
					monitor.checkCancelled();
					Function target = functionAt(targetSpec[0]);
					out.printf("TARGET\t%s\t%s\t%s%n",
						targetSpec[0], targetSpec[1], describe(target));
					List<Function> path = findPath(source, target);
					if (path == null) {
						out.println("PATH\tNOT_FOUND");
					}
					else {
						out.print("PATH");
						for (Function function : path) {
							out.printf("\t%s:%s",
								function.getEntryPoint(), function.getName());
						}
						out.println();
					}
				}
				out.println();
			}
		}
	}

	private Function functionAt(String addressText) {
		Address address = toAddr(addressText);
		Function function = getFunctionAt(address);
		if (function == null) {
			function = getFunctionContaining(address);
		}
		return function;
	}

	private String describe(Function function) {
		if (function == null) {
			return "NO_FUNCTION";
		}
		return function.getEntryPoint() + ":" + function.getName();
	}

	private List<Function> findPath(Function source, Function target) throws Exception {
		if (source == null || target == null) {
			return null;
		}

		ArrayDeque<PathNode> queue = new ArrayDeque<>();
		Set<Address> visited = new HashSet<>();
		List<Function> initialPath = new ArrayList<>();
		initialPath.add(source);
		queue.add(new PathNode(source, initialPath));
		visited.add(source.getEntryPoint());

		while (!queue.isEmpty()) {
			monitor.checkCancelled();
			PathNode node = queue.removeFirst();
			if (node.function.getEntryPoint().equals(target.getEntryPoint())) {
				return node.path;
			}
			if (node.path.size() - 1 >= MAX_DEPTH) {
				continue;
			}
			for (Function callee : node.function.getCalledFunctions(monitor)) {
				if (!visited.add(callee.getEntryPoint())) {
					continue;
				}
				List<Function> nextPath = new ArrayList<>(node.path);
				nextPath.add(callee);
				queue.addLast(new PathNode(callee, nextPath));
			}
		}
		return null;
	}
}
