// Coalesces Ghidra's static code/data/undefined classification for a raw firmware image.
// @category TufAio

import java.io.File;
import java.io.PrintWriter;
import java.util.LinkedHashMap;
import java.util.Map;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Instruction;

public class ExportMemoryClassification extends GhidraScript {
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

		Map<String, Long> totals = new LinkedHashMap<>();
		totals.put("CODE", 0L);
		totals.put("DATA", 0L);
		totals.put("UNDEFINED", 0L);

		try (PrintWriter out = new PrintWriter(output, "UTF-8")) {
			out.println("PROGRAM\t" + currentProgram.getName());
			out.println("NOTE\tThis is Ghidra's current static classification, not a confirmed section map.");
			out.println("START\tEND\tLENGTH\tCLASS");

			Address current = currentProgram.getMinAddress();
			Address maximum = currentProgram.getMaxAddress();
			Address runStart = current;
			String runClass = classify(current);

			while (current.compareTo(maximum) < 0) {
				monitor.checkCancelled();
				Address next = current.next();
				String nextClass = classify(next);
				if (!nextClass.equals(runClass)) {
					long length = current.subtract(runStart) + 1;
					out.printf("%s\t%s\t0x%x\t%s%n",
						runStart, current, length, runClass);
					totals.put(runClass, totals.get(runClass) + length);
					runStart = next;
					runClass = nextClass;
				}
				current = next;
			}

			long length = current.subtract(runStart) + 1;
			out.printf("%s\t%s\t0x%x\t%s%n",
				runStart, current, length, runClass);
			totals.put(runClass, totals.get(runClass) + length);

			out.println();
			for (Map.Entry<String, Long> entry : totals.entrySet()) {
				out.printf("TOTAL\t%s\t0x%x\t%d%n",
					entry.getKey(), entry.getValue(), entry.getValue());
			}
		}
	}

	private String classify(Address address) {
		Instruction instruction = currentProgram.getListing().getInstructionContaining(address);
		if (instruction != null) {
			return "CODE";
		}
		Data data = currentProgram.getListing().getDefinedDataContaining(address);
		if (data != null) {
			return "DATA";
		}
		return "UNDEFINED";
	}
}
